"""Answer-key endpoints: upload → parse (background) → review."""

from __future__ import annotations

import hashlib
import inspect
import logging
import shutil

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from answer_eval.answerkey.converters import UnsupportedAnswerKeyError, convert_source, detect_format
from answer_eval.answerkey.diagrams import extract_diagram_crops
from answer_eval.api.deps import CurrentTeacher, require_database
from answer_eval.db.repositories import answer_keys as ak_repo
from answer_eval.db.repositories import assessments as assessments_repo

logger = logging.getLogger(__name__)

router = APIRouter(tags=["answer-keys"])

MAX_KEY_BYTES = 50 * 1024 * 1024


async def _parser(request: Request):
    """Resolve the parser agent. The factory may be sync (tests inject
    `FakeAnswerKeyParserAgent`) or an async callable that awaits provider
    initialization on first use (the live default)."""
    factory = getattr(request.app.state, "answer_key_parser_factory", None)
    if factory is None:
        raise HTTPException(status_code=503, detail="Answer-key parser unavailable")
    agent = factory()
    if inspect.isawaitable(agent):
        agent = await agent
    return agent


async def _parse_job(
    request: Request,
    key_id: str,
    source_format: str,
    source_bytes: bytes,
) -> None:
    """Runs on the event loop via BackgroundTasks; status lands in the DB."""
    database = require_database(request)
    storage = request.app.state.storage
    try:
        document = convert_source(f"key.{source_format}", source_bytes)

        # For PDFs we need original bytes for rendering; converters keep text only.
        pdf_bytes = source_bytes if source_format == "pdf" else None

        crops = extract_diagram_crops(document, pdf_bytes)
        stored_crops: list[dict] = []
        for crop in crops:
            object_key = storage.put(
                "key-diagrams",
                f"{key_id}/p{crop.page}-{crop.ordinal_on_page}.png",
                crop.png_bytes,
                content_type="image/png",
            )
            stored_crops.append(
                {
                    "page": crop.page,
                    "bbox": crop.bbox,
                    "image_object_key": object_key,
                    "uncertain": False,
                }
            )

        agent = await _parser(request)
        parsed = await agent.parse(document)
        await ak_repo.save_parsed(
            database.pool,
            key_id=key_id,
            parsed=parsed,
            parser_model=getattr(agent, "last_model_id", None),
            prompt_version=getattr(agent, "prompt_version", "unknown"),
            diagrams=stored_crops,
        )
    except (UnsupportedAnswerKeyError, ValueError) as exc:
        logger.warning("Answer-key parse failed for %s: %s", key_id, exc)
        await ak_repo.set_status(database.pool, key_id, "failed", error=str(exc)[:500])
    except Exception as exc:  # noqa: BLE001 - background task must never crash silently
        logger.exception("Unexpected answer-key parse failure for %s", key_id)
        detail = f"{type(exc).__name__}: {exc}"
        await ak_repo.set_status(
            database.pool,
            key_id,
            "failed",
            error=f"Parser crashed ({detail[:180]})",
        )


@router.post("/assessments/{assessment_id}/answer-key", status_code=status.HTTP_202_ACCEPTED)
async def upload_answer_key(
    assessment_id: str,
    request: Request,
    teacher: CurrentTeacher,
    background: BackgroundTasks,
    file: UploadFile,
) -> dict:
    database = require_database(request)
    await assessments_repo.require_owned(
        database.pool, assessment_id=assessment_id, teacher_id=teacher.profile_id
    )

    filename = file.filename or "answer-key.pdf"
    data = await file.read()
    if len(data) > MAX_KEY_BYTES:
        raise HTTPException(status_code=413, detail="Answer key exceeds 50 MB limit")

    try:
        source_format = detect_format(filename)
    except UnsupportedAnswerKeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if source_format == "doc" and not (shutil.which("soffice") or shutil.which("libreoffice")):
        raise HTTPException(status_code=422, detail="Legacy .doc requires LibreOffice on the server; upload PDF/DOCX instead")

    sha256 = hashlib.sha256(data).hexdigest()
    object_key = request.app.state.storage.put(
        "answer-keys",
        f"{assessment_id}/{sha256[:12]}-{safe_filename(filename)}",
        data,
    )
    version = await ak_repo.next_version(database.pool, assessment_id)
    record = await ak_repo.create(
        database.pool,
        assessment_id=assessment_id,
        version=version,
        source_object_key=object_key,
        source_format=source_format,
        source_sha256=sha256,
        created_by=teacher.profile_id,
    )
    background.add_task(_parse_job, request, record["id"], source_format, data)
    return {"answer_key": record}


def safe_filename(filename: str) -> str:
    keep = "".join(ch if ch.isalnum() or ch in ".-_" else "_" for ch in filename)
    return keep[:80]


@router.get("/assessments/{assessment_id}/answer-key")
async def get_latest_key(assessment_id: str, request: Request, teacher: CurrentTeacher) -> dict:
    database = require_database(request)
    await assessments_repo.require_owned(
        database.pool, assessment_id=assessment_id, teacher_id=teacher.profile_id
    )
    meta = await ak_repo.get_for_assessment(database.pool, assessment_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="No answer key uploaded yet")
    questions = await ak_repo.get_questions(database.pool, meta["id"])
    return {"answer_key": meta, "questions": questions}


@router.get("/answer-keys/{key_id}")
async def get_key(key_id: str, request: Request, teacher: CurrentTeacher) -> dict:
    database = require_database(request)
    meta = await ak_repo.get_meta(database.pool, key_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Answer key not found")
    await assessments_repo.require_owned(
        database.pool, assessment_id=meta["assessment_id"], teacher_id=teacher.profile_id
    )
    questions = await ak_repo.get_questions(database.pool, key_id)
    return {"answer_key": meta, "questions": questions}


@router.get("/answer-keys/{key_id}/diagrams/{diagram_id}.png")
async def get_diagram_image(key_id: str, diagram_id: str, request: Request, teacher: CurrentTeacher) -> StreamingResponse:
    database = require_database(request)
    meta = await ak_repo.get_meta(database.pool, key_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Answer key not found")
    await assessments_repo.require_owned(
        database.pool, assessment_id=meta["assessment_id"], teacher_id=teacher.profile_id
    )
    object_key = await ak_repo.get_diagram_image_key(database.pool, key_id, diagram_id)
    if not object_key:
        raise HTTPException(status_code=404, detail="Diagram not found")
    storage = request.app.state.storage

    def iterator():
        with storage.open(object_key) as handle:
            while chunk := handle.read(256 * 1024):
                yield chunk

    return StreamingResponse(iterator(), media_type="image/png")


class QuestionReviewEdit(BaseModel):
    question_number: int = Field(ge=1)
    question_text: str | None = None
    expected_answer_text: str | None = None
    maximum_marks: float | None = Field(default=None, ge=0)
    answer_type: str | None = None
    keywords: list[str] | None = None
    mandatory_terms: list[str] | None = None
    math_rubric: list[dict] | None = None


class ReviewIn(BaseModel):
    edits: list[QuestionReviewEdit] = []
    confirm: bool = True


@router.patch("/answer-keys/{key_id}/review")
async def review_key(key_id: str, body: ReviewIn, request: Request, teacher: CurrentTeacher) -> dict:
    database = require_database(request)
    meta = await ak_repo.get_meta(database.pool, key_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Answer key not found")
    await assessments_repo.require_owned(
        database.pool, assessment_id=meta["assessment_id"], teacher_id=teacher.profile_id
    )
    if meta["status"] == "parsing":
        raise HTTPException(status_code=409, detail="Parser still running; poll until it finishes")
    if body.edits:
        await ak_repo.apply_review_edits(
            database.pool,
            key_id=key_id,
            edits=[edit.model_dump(exclude_none=False) for edit in body.edits],
        )
    elif body.confirm and meta["status"] == "parsed":
        await ak_repo.set_status(database.pool, key_id, "reviewed")
    questions = await ak_repo.get_questions(database.pool, key_id)
    return {"answer_key": {**(await ak_repo.get_meta(database.pool, key_id))}, "questions": questions}
