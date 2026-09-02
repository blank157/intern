"""Assessment + ingestion endpoints (Milestone 3)."""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from answer_eval.api.deps import CurrentTeacher, require_database
from answer_eval.db.repositories import answer_keys as ak_repo
from answer_eval.db.repositories import assessments as assessments_repo
from answer_eval.db.repositories import submissions as submissions_repo
from answer_eval.ingestion.service import IngestionError, StudentZipIngestionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assessments", tags=["assessments"])


class CreateAssessmentIn(BaseModel):
    title: str | None = None


class AssessmentDetailsIn(BaseModel):
    title: str | None = None
    class_name: str | None = Field(default=None, max_length=120)
    subject_name: str | None = Field(default=None, max_length=120)
    pass_percentage: float | None = Field(default=None, ge=0, le=100)


class ReviewDecisionIn(BaseModel):
    approved: bool = True
    final_marks: float | None = Field(default=None, ge=0)
    reviewer_notes: str | None = None


class ReviewDecisionsIn(BaseModel):
    decisions: dict[str, ReviewDecisionIn]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_draft_assessment(
    body: CreateAssessmentIn,
    request: Request,
    teacher: CurrentTeacher,
) -> dict:
    database = require_database(request)
    draft = await assessments_repo.create_draft(
        database.pool, teacher_id=teacher.profile_id, title=body.title or ""
    )
    created = await assessments_repo.get(database.pool, draft["id"])
    return {"assessment": created}


@router.get("")
async def list_assessments(request: Request, teacher: CurrentTeacher) -> list[dict]:
    database = require_database(request)
    return await assessments_repo.list_for_teacher(database.pool, teacher.profile_id)


@router.get("/{assessment_id}")
async def get_assessment(assessment_id: str, request: Request, teacher: CurrentTeacher) -> dict:
    database = require_database(request)
    try:
        await assessments_repo.require_owned(
            database.pool, assessment_id=assessment_id, teacher_id=teacher.profile_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Assessment not found") from exc
    assessment = await assessments_repo.get(database.pool, assessment_id)
    summary = await submissions_repo.count_summary(database.pool, assessment_id)
    return {"assessment": assessment, "summary": summary}


@router.patch("/{assessment_id}")
async def update_assessment_details(
    assessment_id: str,
    body: AssessmentDetailsIn,
    request: Request,
    teacher: CurrentTeacher,
) -> dict:
    database = require_database(request)
    try:
        updated = await assessments_repo.update_details(
            database.pool,
            assessment_id=assessment_id,
            teacher_id=teacher.profile_id,
            title=body.title,
            class_name=body.class_name,
            subject_name=body.subject_name,
            pass_percentage=body.pass_percentage,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return {"assessment": updated}


@router.delete("/{assessment_id}")
async def delete_draft_assessment(
    assessment_id: str,
    request: Request,
    teacher: CurrentTeacher,
) -> dict:
    database = require_database(request)
    deleted = await assessments_repo.delete_draft(
        database.pool, assessment_id=assessment_id, teacher_id=teacher.profile_id
    )
    if not deleted:
        raise HTTPException(status_code=409, detail="Only drafts can be deleted")
    return {"deleted": True}


@router.post("/{assessment_id}/student-zip")
async def upload_student_zip(
    assessment_id: str,
    request: Request,
    teacher: CurrentTeacher,
    file: UploadFile,
) -> dict:
    database = require_database(request)
    payload = await file.read()
    service = StudentZipIngestionService(database.pool, request.app.state.storage)
    try:
        result = await service.ingest(
            assessment_id=assessment_id,
            teacher_id=teacher.profile_id,
            zip_bytes=payload,
        )
    except IngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result.to_dict()


@router.get("/{assessment_id}/students")
async def list_students(assessment_id: str, request: Request, teacher: CurrentTeacher) -> list[dict]:
    database = require_database(request)
    try:
        await assessments_repo.require_owned(
            database.pool, assessment_id=assessment_id, teacher_id=teacher.profile_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Assessment not found") from exc
    return await submissions_repo.list_for_assessment(database.pool, assessment_id)


# ---------------------------------------------------------------------------
# Milestone 6: evaluation start + status polling + add answer paper
# ---------------------------------------------------------------------------


async def _owned_assessment(database, assessment_id: str, teacher_profile_id: str) -> dict:
    try:
        return await assessments_repo.require_owned(
            database.pool, assessment_id=assessment_id, teacher_id=teacher_profile_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Assessment not found") from exc


@router.post("/{assessment_id}/start", status_code=status.HTTP_202_ACCEPTED)
async def begin_evaluation(
    assessment_id: str,
    request: Request,
    teacher: CurrentTeacher,
) -> dict:
    """Queue all uploaded papers for evaluation and return immediately.

    The HTTP request never blocks on grading; workers pick up queued
    submissions asynchronously.
    """
    database = require_database(request)
    assessment = await _owned_assessment(database, assessment_id, teacher.profile_id)

    if assessment["status"] == "processing":
        raise HTTPException(status_code=409, detail="Evaluation is already running")
    if assessment["status"] != "configured":
        raise HTTPException(
            status_code=409,
            detail=f"Save (finalize) the assessment before starting evaluation "
            f"(current status: {assessment['status']})",
        )
    if not assessment.get("locked_answer_key_version") or not assessment.get("locked_policy_version"):
        raise HTTPException(status_code=409, detail="Locked answer-key/policy versions are missing")

    summary = await submissions_repo.count_summary(database.pool, assessment_id)
    if summary["ready"] == 0:
        raise HTTPException(status_code=422, detail="Upload at least one valid student paper before starting")

    queued = await submissions_repo.queue_uploaded(database.pool, assessment_id)
    updated = await assessments_repo.set_status(
        database.pool,
        assessment_id=assessment_id,
        teacher_id=teacher.profile_id,
        new_status="processing",
        allowed_from=("configured",),
    )
    if updated is None:  # pragma: no cover - race with another start call
        raise HTTPException(status_code=409, detail="Assessment is not in a startable state")

    # --- The bridge to the durable job store --------------------------------
    # Convert the frozen resolved policies into workflow rubric + teacher rules
    # ONCE, then enqueue one durable job per queued submission. The HTTP request
    # still never blocks on grading — a separate worker (the same machine or a
    # distributed fleet) claims these jobs from the durable store.
    from answer_eval.db.repositories import policies as policies_repo
    from answer_eval.grading.hydrate import build_workflow_inputs

    job_service = getattr(request.app.state, "job_service", None)
    storage = request.app.state.storage
    storage_root = getattr(storage, "_root", None)

    jobs_created = 0
    if job_service is not None and storage_root is not None:
        resolved = await policies_repo.get_resolved(database.pool, assessment_id=assessment_id)
        rubrics, teacher_rules = build_workflow_inputs(resolved)

        roster = await submissions_repo.list_for_assessment(database.pool, assessment_id)
        for item in roster:
            if item["status"] != "queued":
                continue
            object_key = item.get("pdf_object_key")
            if not object_key:
                logger.warning("Skipping submission without a stored PDF", submission_id=item["id"])
                continue
            pdf_path = str(Path(storage_root) / object_key)
            job_service.submit(
                submission_id=item["id"],
                pdf_path=pdf_path,
                rubrics=rubrics,
                teacher_rules=teacher_rules,
            )
            jobs_created += 1
    elif getattr(request.app.state, "database", None) is not None:
        raise HTTPException(
            status_code=503,
            detail="Worker job store unavailable: the single-node bridge needs local file storage "
            "(configure STORAGE_LOCAL_ROOT and restart the API).",
        )

    return {
        "assessment_id": assessment_id,
        "status": "processing",
        "submissions_queued": queued,
        "jobs_enqueued": jobs_created,
    }


@router.get("/{assessment_id}/status")
async def get_assessment_status(assessment_id: str, request: Request, teacher: CurrentTeacher) -> dict:
    """Lightweight polling endpoint for incremental progress in the UI."""
    database = require_database(request)
    assessment = await _owned_assessment(database, assessment_id, teacher.profile_id)
    summary = await submissions_repo.count_summary(database.pool, assessment_id)
    students = [
        {
            "submission_id": str(item["id"]),
            "roll_number": item["roll_number"],
            "status": item["status"],
            "status_detail": item.get("status_detail"),
        }
        for item in await submissions_repo.list_for_assessment(database.pool, assessment_id)
    ]
    key_meta = await ak_repo.get_for_assessment(database.pool, assessment_id)
    answer_key = (
        {
            "id": str(key_meta["id"]),
            "status": key_meta["status"],
            "version": int(key_meta["version"]),
        }
        if key_meta
        else None
    )
    return {
        "assessment_id": assessment_id,
        "status": assessment["status"],
        "total_marks": float(assessment.get("total_marks") or 0),
        "pass_percentage": float(assessment.get("pass_percentage") or 0),
        "summary": summary,
        "students": students,
        "answer_key": answer_key,
    }


@router.post("/{assessment_id}/submissions", status_code=status.HTTP_201_CREATED)
async def add_answer_paper(
    assessment_id: str,
    request: Request,
    teacher: CurrentTeacher,
    file: UploadFile,
) -> dict:
    """Add one missing student PDF to a not-yet-started assessment.

    Reuses the secure ZIP ingestion pipeline by wrapping the single file into an
    in-memory archive so roll-number parsing, PDF validation and duplicate
    detection stay identical.
    """
    database = require_database(request)
    assessment = await _owned_assessment(database, assessment_id, teacher.profile_id)
    if assessment["status"] not in ("draft", "configured"):
        raise HTTPException(status_code=409, detail="Answer sheets can only be added before evaluation starts")

    payload = await file.read()
    original_name = Path(file.filename or "paper.pdf").name or "paper.pdf"
    stem = Path(original_name).stem or "paper"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{stem}.pdf", payload)

    service = StudentZipIngestionService(database.pool, request.app.state.storage)
    try:
        result = await service.ingest(
            assessment_id=assessment_id,
            teacher_id=teacher.profile_id,
            zip_bytes=buffer.getvalue(),
        )
    except IngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result.valid == 0:
        first = result.students[0] if result.students else {}
        reason = first.get("reason") or "file could not be accepted"
        raise HTTPException(status_code=422, detail=f"Rejected '{original_name}': {reason}")
    return result.to_dict()


@router.get("/{assessment_id}/results")
async def get_results(assessment_id: str, request: Request, teacher: CurrentTeacher) -> dict:
    """Incremental results read-model (#70/#73): real status per student."""
    database = require_database(request)
    try:
        await assessments_repo.require_owned(
            database.pool, assessment_id=assessment_id, teacher_id=teacher.profile_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Assessment not found") from exc
    from answer_eval.db.repositories import results as results_repo

    return await results_repo.assessment_results(database.pool, assessment_id)


@router.get("/{assessment_id}/results/{submission_id}")
async def get_submission_result(
    assessment_id: str,
    submission_id: str,
    request: Request,
    teacher: CurrentTeacher,
) -> dict:
    """Question-level result detail (#74) from durable final/evaluation results."""
    database = require_database(request)
    try:
        await assessments_repo.require_owned(
            database.pool, assessment_id=assessment_id, teacher_id=teacher.profile_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Assessment not found") from exc
    from answer_eval.db.repositories import results as results_repo

    detail = await results_repo.submission_results(database.pool, submission_id)
    if not detail or str(detail.get("assessment_id") if detail.get("assessment_id") else "") != assessment_id:
        # submission belongs to this assessment? verify explicitly.
        check = await database.pool.fetchval(
            "select assessment_id::text from submissions where id = $1::uuid",
            __import__("uuid").UUID(submission_id),
        )
        if check != assessment_id:
            raise HTTPException(status_code=404, detail="Submission not found in this assessment")
        detail = await results_repo.submission_results(database.pool, submission_id)
    return {"assessment_id": assessment_id, **detail}


@router.get("/submissions/{submission_id}/review-request")
async def get_submission_review_request(
    submission_id: str,
    request: Request,
    teacher: CurrentTeacher,
) -> dict:
    """Teacher-facing pending review payload for a submission's active job.

    Returns the questions the risk engine routed to human review, with the AI's
    proposed marks, so the UI can render an approval panel.
    """
    database = require_database(request)
    job_service = getattr(request.app.state, "job_service", None)
    if job_service is None:
        raise HTTPException(status_code=503, detail="Job store unavailable")
    row = await database.pool.fetchrow(
        "select assessment_id::text from submissions where id = $1::uuid",
        submission_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    try:
        await assessments_repo.require_owned(
            database.pool, assessment_id=row["assessment_id"], teacher_id=teacher.profile_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Submission not found") from exc
    job = job_service.store.find_active_by_submission(submission_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No active evaluation job for this submission")
    return {
        "job_id": job.job_id,
        "status": job.status.value,
        "review_request": job.review_request,
    }


@router.post("/submissions/{submission_id}/review")
async def submit_submission_review(
    submission_id: str,
    body: ReviewDecisionsIn,
    request: Request,
    teacher: CurrentTeacher,
) -> dict:
    """Apply teacher review decisions and resume the waiting evaluation job."""
    database = require_database(request)
    job_service = getattr(request.app.state, "job_service", None)
    if job_service is None:
        raise HTTPException(status_code=503, detail="Job store unavailable")
    row = await database.pool.fetchrow(
        "select assessment_id::text from submissions where id = $1::uuid",
        submission_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    try:
        await assessments_repo.require_owned(
            database.pool, assessment_id=row["assessment_id"], teacher_id=teacher.profile_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Submission not found") from exc
    job = job_service.store.find_active_by_submission(submission_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No active evaluation job for this submission")
    from answer_eval.core.errors import JobError
    from answer_eval.jobs.schemas import JobStatus

    try:
        decisions = {
            qid: decision.model_dump(exclude_none=True)
            for qid, decision in body.decisions.items()
        }
        job_service.resume_after_review(job.job_id, decisions)
    except JobError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"job_id": job.job_id, "status": JobStatus.queued.value}


@router.get("/submissions/{submission_id}/pdf")
async def download_submission_pdf(
    submission_id: str,
    request: Request,
    teacher: CurrentTeacher,
) -> StreamingResponse:
    """Streams the original PDF after ownership verification."""
    database = require_database(request)
    submission = await submissions_repo.get_submission(database.pool, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    try:
        await assessments_repo.require_owned(
            database.pool,
            assessment_id=str(submission["assessment_id"]),
            teacher_id=teacher.profile_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Submission not found") from exc
    storage = request.app.state.storage
    key = str(submission["pdf_object_key"])

    def iterator():
        with storage.open(key) as handle:
            while chunk := handle.read(1024 * 256):
                yield chunk

    return StreamingResponse(iterator(), media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{submission["roll_number"]}.pdf"'
    })
