"""Answer-key persistence: versions, parsed questions, diagram crops."""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg

from answer_eval.answerkey.schemas import ParsedAnswerKey


def _uuid(value: str) -> uuid.UUID:
    return uuid.UUID(str(value))


def _row_to_dict(row: asyncpg.Record | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    data["id"] = str(data["id"])
    if data.get("assessment_id") is not None:
        data["assessment_id"] = str(data["assessment_id"])
    return data


async def create(
    pool: asyncpg.Pool,
    *,
    assessment_id: str,
    version: int,
    source_object_key: str,
    source_format: str,
    source_sha256: str,
    created_by: str,
) -> dict[str, Any]:
    row = await pool.fetchrow(
        """
        insert into answer_keys
            (assessment_id, version, source_object_key, source_format, source_sha256, status, created_by)
        values ($1, $2, $3, $4, $5, 'parsing', $6)
        returning id, assessment_id, version, status
        """,
        _uuid(assessment_id),
        version,
        source_object_key,
        source_format,
        source_sha256,
        _uuid(created_by),
    )
    result = _row_to_dict(row)
    assert result is not None
    return result


async def set_status(pool: asyncpg.Pool, key_id: str, status: str, *, error: str | None = None) -> None:
    await pool.execute(
        "update answer_keys set status = $2, parse_error = $3, updated_at = now() where id = $1",
        _uuid(key_id),
        status,
        error,
    )


async def save_parsed(
    pool: asyncpg.Pool,
    *,
    key_id: str,
    parsed: ParsedAnswerKey,
    parser_model: str | None,
    prompt_version: str,
    diagrams: list[dict[str, Any]],
) -> None:
    """Persist parsed payload + question rows + stored diagram crops atomically."""
    allowed_types = {"descriptive", "explain", "short_answer", "numerical", "formula", "diagram", "mixed"}
    async with pool.acquire() as connection, connection.transaction():
        await connection.execute("delete from questions where answer_key_id = $1", _uuid(key_id))
        await connection.execute(
            """
            update answer_keys
            set raw_parser_json = $2, parser_model = $3, parser_prompt_version = $4,
                schema_version = $5, status = 'parsed', parse_error = null, updated_at = now()
            where id = $1
            """,
            _uuid(key_id),
            parsed.model_dump(),
            parser_model,
            prompt_version,
            parsed.schema_version,
        )
        for question in sorted(parsed.questions, key=lambda q: q.question_number):
            qrow = await connection.fetchrow(
                """
                insert into questions (answer_key_id, question_number, ordinal, question_text,
                                       maximum_marks, answer_type, expected_answer_text,
                                       math_rubric, parser_uncertainties)
                values ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                returning id
                """,
                _uuid(key_id),
                question.question_number,
                question.question_number,
                question.question_text,
                question.maximum_marks,
                question.answer_type if question.answer_type in allowed_types else "descriptive",
                question.expected_answer_text,
                [s.model_dump() for s in question.math_rubric] if question.math_rubric else None,
                question.parser_uncertainties,
            )
            assert qrow is not None
            question_id = qrow["id"]

            for concept in question.expected_concepts:
                await connection.execute(
                    """
                    insert into expected_concepts (question_id, concept_code, description, maximum_marks, ordinal)
                    values ($1, $2, $3, $4, $5)
                    on conflict (question_id, concept_code) do nothing
                    """,
                    question_id,
                    concept.concept_code,
                    concept.description,
                    concept.maximum_marks,
                    len(concept.concept_code),
                )
            for term in question.keywords:
                await connection.execute(
                    "insert into keywords (question_id, term) values ($1, $2) on conflict do nothing",
                    question_id,
                    term,
                )
            for term in question.mandatory_terms:
                await connection.execute(
                    "insert into mandatory_terms (question_id, term) values ($1, $2) on conflict do nothing",
                    question_id,
                    term,
                )
            if question.diagram_hints:
                labels = [hint.type_label for hint in question.diagram_hints if hint.type_label]
                await connection.execute(
                    """
                    insert into diagram_requirements
                        (question_id, required, count_required, required_labels, required_components, notes)
                    values ($1, true, $2, $3, '[]', 'Derived from answer-key diagram hints')
                    on conflict do nothing
                    """,
                    question_id,
                    len(question.diagram_hints),
                    labels,
                )

        # Diagram crops: attach to questions in hint order; leftovers go to Q1.
        flat_hints = [
            (question.question_number, hint)
            for question in sorted(parsed.questions, key=lambda x: x.question_number)
            for hint in question.diagram_hints
        ]
        hint_index = 0
        for crop in diagrams:
            if hint_index < len(flat_hints):
                assigned_question_number, hint = flat_hints[hint_index]
                hint_index += 1
            else:
                assigned_question_number = min((q.question_number for q in parsed.questions), default=1)
                hint = None
            qid = await connection.fetchval(
                "select id from questions where answer_key_id = $1 and question_number = $2",
                _uuid(key_id),
                assigned_question_number,
            )
            if qid is None:
                continue
            ordinal_row = await connection.fetchval(
                "select coalesce(max(ordinal), 0) + 1 from answer_key_diagrams where question_id = $1",
                qid,
            )
            await connection.execute(
                """
                insert into answer_key_diagrams
                    (question_id, diagram_code, ordinal, type_label, image_object_key, source_page, bbox, parser_uncertain)
                values ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                qid,
                f"Q{assigned_question_number}-D{ordinal_row}",
                ordinal_row,
                getattr(hint, "type_label", None) if hint is not None else None,
                crop["image_object_key"],
                crop.get("page"),
                crop.get("bbox") or [],
                bool(getattr(hint, "uncertain", False)) or bool(crop.get("uncertain")),
            )


async def get_meta(pool: asyncpg.Pool, key_id: str) -> dict[str, Any] | None:
    row = await pool.fetchrow(
        """
        select id, assessment_id, version, source_object_key, source_format, status,
               parse_error, parser_model, parser_prompt_version, schema_version, raw_parser_json, created_at
        from answer_keys where id = $1
        """,
        _uuid(key_id),
    )
    result = _row_to_dict(row)
    if result is not None and row is not None and row["created_at"] is not None:
        result["created_at"] = row["created_at"].isoformat()
    return result


async def get_for_assessment(pool: asyncpg.Pool, assessment_id: str) -> dict[str, Any] | None:
    row = await pool.fetchrow(
        "select id from answer_keys where assessment_id = $1 order by version desc limit 1",
        _uuid(assessment_id),
    )
    if row is None:
        return None
    return await get_meta(pool, str(row["id"]))


async def get_questions(pool: asyncpg.Pool, key_id: str) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        """
        select q.id, q.question_number, q.question_text, q.maximum_marks, q.answer_type,
               q.expected_answer_text, q.math_rubric, q.parser_uncertainties,
               coalesce((
                   select jsonb_agg(jsonb_build_object(
                       'concept_code', c.concept_code, 'description', c.description,
                       'maximum_marks', c.maximum_marks) order by c.ordinal)
                   from expected_concepts c where c.question_id = q.id
               ), '[]'::jsonb) as concepts,
               coalesce((select jsonb_agg(k.term) from keywords k where k.question_id = q.id), '[]'::jsonb) as keywords,
               coalesce((select jsonb_agg(m.term) from mandatory_terms m where m.question_id = q.id), '[]'::jsonb) as mandatory_terms,
               coalesce((select jsonb_agg(jsonb_build_object(
                   'id', d.id, 'diagram_code', d.diagram_code, 'ordinal', d.ordinal,
                   'type_label', d.type_label, 'source_page', d.source_page,
                   'bbox', d.bbox, 'parser_uncertain', d.parser_uncertain) order by d.ordinal)
               from answer_key_diagrams d where d.question_id = q.id), '[]'::jsonb) as diagrams
        from questions q
        where q.answer_key_id = $1
        order by q.question_number
        """,
        _uuid(key_id),
    )
    results = []
    for row in rows:
        item = dict(row)
        item["id"] = str(item["id"])
        item["math_rubric"] = item["math_rubric"] or []
        item["parser_uncertainties"] = item["parser_uncertainties"] or []
        for diagram in item["diagrams"]:
            diagram["id"] = str(diagram["id"])
        results.append(item)
    return results


async def get_diagram_image_key(pool: asyncpg.Pool, key_id: str, diagram_id: str) -> str | None:
    return await pool.fetchval(
        """
        select d.image_object_key from answer_key_diagrams d
        join questions q on q.id = d.question_id
        where q.answer_key_id = $1 and d.id = $2
        """,
        _uuid(key_id),
        _uuid(diagram_id),
    )


async def apply_review_edits(
    pool: asyncpg.Pool,
    *,
    key_id: str,
    edits: list[dict[str, Any]],
) -> None:
    """Teacher corrections from the review step."""
    async with pool.acquire() as connection, connection.transaction():
        for edit in edits:
            qid = await connection.fetchval(
                "select id from questions where answer_key_id = $1 and question_number = $2",
                _uuid(key_id),
                int(edit["question_number"]),
            )
            if qid is None:
                continue
            assignments: list[str] = []
            values: list[Any] = []

            def _set(column: str, value: Any, assignments: list[str] = assignments, values: list[Any] = values) -> None:
                assignments.append(f"{column} = ${len(values) + 1}")
                values.append(value)

            if edit.get("question_text") is not None:
                _set("question_text", edit["question_text"])
            if edit.get("expected_answer_text") is not None:
                _set("expected_answer_text", edit["expected_answer_text"])
            if edit.get("maximum_marks") is not None:
                _set("maximum_marks", float(edit["maximum_marks"]))
            if edit.get("answer_type") is not None:
                _set("answer_type", edit["answer_type"])
            if edit.get("math_rubric") is not None:
                _set("math_rubric", edit["math_rubric"])
            if assignments:
                values.append(qid)
                await connection.execute(
                    f"update questions set {', '.join(assignments)} where id = ${len(values)}",
                    *values,
                )
            if edit.get("keywords") is not None:
                await connection.execute("delete from keywords where question_id = $1", qid)
                for term in edit["keywords"]:
                    await connection.execute(
                        "insert into keywords (question_id, term) values ($1, $2) on conflict do nothing",
                        qid,
                        term,
                    )
            if edit.get("mandatory_terms") is not None:
                await connection.execute("delete from mandatory_terms where question_id = $1", qid)
                for term in edit["mandatory_terms"]:
                    await connection.execute(
                        "insert into mandatory_terms (question_id, term) values ($1, $2) on conflict do nothing",
                        qid,
                        term,
                    )
        await connection.execute(
            "update answer_keys set status = 'reviewed', updated_at = now() where id = $1",
            _uuid(key_id),
        )


async def next_version(pool: asyncpg.Pool, assessment_id: str) -> int:
    current = await pool.fetchval(
        "select max(version) from answer_keys where assessment_id = $1",
        _uuid(assessment_id),
    )
    return int(current or 0) + 1
