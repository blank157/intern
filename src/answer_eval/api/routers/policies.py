"""Policy configuration + finalize endpoints (Milestone 5)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from answer_eval.api.deps import CurrentTeacher, require_database
from answer_eval.db.repositories import answer_keys as ak_repo
from answer_eval.db.repositories import assessments as assessments_repo
from answer_eval.db.repositories import policies as policies_repo
from answer_eval.db.repositories import submissions as submissions_repo
from answer_eval.grading.policy_resolution import (
    DiagramRule,
    PolicyValidationError,
    StrictnessRule,
    WordCountRule,
    validate_rules,
)

router = APIRouter(prefix="/assessments", tags=["policies"])


class StrictnessRuleIn(BaseModel):
    question: int | None = Field(default=None, ge=1)
    from_q: int | None = Field(default=None, ge=1, alias="from")
    to_q: int | None = Field(default=None, ge=1, alias="to")
    level: str

    model_config = {"populate_by_name": True}


class WordCountRuleIn(BaseModel):
    question: int | None = Field(default=None, ge=1)
    from_q: int | None = Field(default=None, ge=1, alias="from")
    to_q: int | None = Field(default=None, ge=1, alias="to")
    minimum_words: int = Field(ge=0)
    mode: str = "once"
    shortfall_words: int = Field(default=0, ge=0)
    marks_deducted: float = Field(default=0, ge=0)

    model_config = {"populate_by_name": True}


class DiagramRuleIn(BaseModel):
    question: int | None = Field(default=None, ge=1)
    from_q: int | None = Field(default=None, ge=1, alias="from")
    to_q: int | None = Field(default=None, ge=1, alias="to")
    required: bool
    minimum_diagrams: int = Field(default=1, ge=1)
    missing_diagram_deductions: list[float] = []

    model_config = {"populate_by_name": True}


class PoliciesIn(BaseModel):
    strictness: dict[str, Any] = Field(default_factory=dict)
    word_count: dict[str, Any] = Field(default_factory=dict)
    diagrams: dict[str, Any] = Field(default_factory=dict)


def _rules_from_payload(kind: str, payload: dict[str, Any]):
    rules: list[Any] = []
    for entry in payload.get("questions", []) or []:
        if kind == "strictness":
            rules.append(StrictnessRule(level=str(entry["level"]), question_number=int(entry["question"]), rule_id=f"q{entry['question']}"))
        elif kind == "word_count":
            rules.append(
                WordCountRule(
                    minimum_words=int(entry.get("minimum_words", 0)),
                    mode=str(entry.get("mode", "once")),
                    trigger_shortfall_words=int(entry.get("trigger_shortfall_words", 0)),
                    marks_deducted=float(entry.get("marks_deducted", 0)),
                    question_number=int(entry["question"]),
                    rule_id=f"q{entry['question']}",
                )
            )
        else:
            deductions = [float(v) for v in entry.get("missing_diagram_deductions", [])]
            required = bool(entry.get("required", False))
            minimum = int(entry.get("minimum_diagrams", 1)) if required else 0
            if required and len(deductions) < minimum:
                raise PolicyValidationError(f"Q{entry['question']}: {minimum} deduction value(s) required, got {len(deductions)}")
            rules.append(
                DiagramRule(
                    required=required,
                    minimum_diagrams=minimum or 1,
                    missing_diagram_deductions=tuple(deductions),
                    question_number=int(entry["question"]),
                    rule_id=f"q{entry['question']}",
                )
            )
    for entry in payload.get("ranges", []) or []:
        if kind == "strictness":
            rules.append(
                StrictnessRule(
                    level=str(entry["level"]),
                    question_from=int(entry["from"]),
                    question_to=int(entry["to"]),
                    rule_id=f"r{entry['from']}-{entry['to']}",
                )
            )
        elif kind == "word_count":
            rules.append(
                WordCountRule(
                    minimum_words=int(entry.get("minimum_words", 0)),
                    mode=str(entry.get("mode", "once")),
                    trigger_shortfall_words=int(entry.get("trigger_shortfall_words", 0)),
                    marks_deducted=float(entry.get("marks_deducted", 0)),
                    question_from=int(entry["from"]),
                    question_to=int(entry["to"]),
                    rule_id=f"r{entry['from']}-{entry['to']}",
                )
            )
        else:
            deductions = [float(v) for v in entry.get("missing_diagram_deductions", [])]
            required = bool(entry.get("required", False))
            minimum = int(entry.get("minimum_diagrams", 1)) if required else 0
            if required and len(deductions) < minimum:
                raise PolicyValidationError(f"range Q{entry['from']}–Q{entry['to']}: {minimum} deduction value(s) required, got {len(deductions)}")
            rules.append(
                DiagramRule(
                    required=required,
                    minimum_diagrams=minimum or 1,
                    missing_diagram_deductions=tuple(deductions),
                    question_from=int(entry["from"]),
                    question_to=int(entry["to"]),
                    rule_id=f"r{entry['from']}-{entry['to']}",
                )
            )
    return rules


@router.put("/{assessment_id}/policies")
async def put_policies(assessment_id: str, body: PoliciesIn, request: Request, teacher: CurrentTeacher) -> dict:
    database = require_database(request)
    await assessments_repo.require_owned(
        database.pool, assessment_id=assessment_id, teacher_id=teacher.profile_id
    )

    key_meta = await ak_repo.get_for_assessment(database.pool, assessment_id)
    if key_meta is None or key_meta["status"] not in ("parsed", "reviewed"):
        raise HTTPException(status_code=409, detail="Upload and review the answer key before configuring policies")

    questions = await ak_repo.get_questions(database.pool, key_meta["id"])
    question_count = max((int(q["question_number"]) for q in questions), default=0)

    strictness = _rules_from_payload("strictness", body.strictness)
    word_count = _rules_from_payload("word_count", body.word_count)
    diagrams = _rules_from_payload("diagrams", body.diagrams)
    try:
        validate_rules(
            question_count=question_count,
            strictness_rules=strictness,
            word_count_rules=word_count,
            diagram_rules=diagrams,
        )
    except PolicyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    rubric_snapshots = {
        int(q["question_number"]): {
            "maximum_marks": float(q["maximum_marks"]),
            "answer_type": q["answer_type"],
            "concepts": q["concepts"],
            "keywords": q["keywords"],
            "mandatory_terms": q["mandatory_terms"],
            "math_rubric": q["math_rubric"],
            "answer_key_version": key_meta["version"],
        }
        for q in questions
    }
    resolved, version = await policies_repo.build_and_store_resolution(
        database.pool,
        assessment_id=assessment_id,
        question_numbers=list(range(1, question_count + 1)),
        strictness=strictness,
        word_count=word_count,
        diagrams=diagrams,
        rubric_snapshots=rubric_snapshots,
    )
    return {"policy_version": version, "question_count": question_count, "policies": _public(resolved)}


@router.get("/{assessment_id}/policies/resolved")
async def get_resolved_policies(assessment_id: str, request: Request, teacher: CurrentTeacher) -> dict:
    database = require_database(request)
    await assessments_repo.require_owned(
        database.pool, assessment_id=assessment_id, teacher_id=teacher.profile_id
    )
    resolved = await policies_repo.get_resolved(database.pool, assessment_id=assessment_id)
    total = sum(float(row.get("rubric_snapshot", {}).get("maximum_marks") or 0) for row in resolved)
    return {"policies": _public(resolved), "total_maximum": round(total, 2)}


class FinalizeIn(BaseModel):
    title: str | None = None


@router.post("/{assessment_id}/finalize")
async def finalize_assessment(
    assessment_id: str,
    request: Request,
    teacher: CurrentTeacher,
    body: FinalizeIn | None = None,
) -> dict:
    database = require_database(request)
    assessment = await assessments_repo.require_owned(
        database.pool, assessment_id=assessment_id, teacher_id=teacher.profile_id
    )
    if assessment["status"] not in ("draft", "configured"):
        raise HTTPException(status_code=409, detail=f"Assessment is already {assessment['status']}")
    if not (assessment.get("class_id") and assessment.get("subject_id")):
        raise HTTPException(status_code=422, detail="Select the class and subject before saving")
    if body and body.title:
        assessment = (
            await assessments_repo.update_details(
                database.pool,
                assessment_id=assessment_id,
                teacher_id=teacher.profile_id,
                title=body.title,
            )
            or assessment
        )

    key_meta = await ak_repo.get_for_assessment(database.pool, assessment_id)
    if key_meta is None or key_meta["status"] != "reviewed":
        raise HTTPException(status_code=422, detail="Confirm the parsed answer key before saving (review step)")

    resolved = await policies_repo.get_resolved(database.pool, assessment_id=assessment_id)
    if not resolved:
        raise HTTPException(status_code=422, detail="Configure evaluation policies before saving")

    roster = await submissions_repo.list_for_assessment(database.pool, assessment_id)
    if not any(item["status"] != "invalid" for item in roster):
        raise HTTPException(status_code=422, detail="Upload at least one valid student paper before saving")

    total_maximum = sum(
        float(row.get("rubric_snapshot", {}).get("maximum_marks") or 0) for row in resolved
    )
    latest_version = max(int(row["version"]) for row in resolved)
    if body and body.title:
        await assessments_repo.update_details(
            database.pool,
            assessment_id=assessment_id,
            teacher_id=teacher.profile_id,
            title=body.title,
        )
    await database.pool.execute(
        """
        update assessments
        set status = 'configured',
            question_count = $2::int,
            total_marks = $3,
            locked_answer_key_version = $4::int,
            locked_policy_version = $5::int
        where id = $1
        """,
        uuid.UUID(assessment_id),
        len(resolved),
        round(total_maximum, 2),
        int(key_meta["version"]),
        latest_version,
    )
    final = await assessments_repo.get(database.pool, assessment_id)
    summary = await submissions_repo.count_summary(database.pool, assessment_id)
    return {"assessment": final, "summary": summary}


def _public(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keep = (
        "question_number",
        "version",
        "strictness_level",
        "minimum_words",
        "word_count_mode",
        "trigger_shortfall_words",
        "marks_deducted",
        "diagram_required",
        "min_diagrams",
        "missing_diagram_deductions",
        "source_rule_ids",
        "rubric_snapshot",
    )
    return [{column: row[column] for column in keep} for row in rows]
