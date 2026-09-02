"""Auth-related backend endpoints (token verification + profile sync).

Signup/login/password flows run against Supabase Auth directly from the
frontend (anon key); the backend only verifies JWTs and mirrors identity into
public.profiles.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from answer_eval.api.deps import CurrentTeacher, require_database
from answer_eval.api.models import MeOut, ProfileOut, SyncProfileIn
from answer_eval.db.repositories import profiles as profiles_repo

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=MeOut)
async def me(request: Request, teacher: CurrentTeacher) -> MeOut:
    database = require_database(request)
    row = await profiles_repo.get_profile(database.pool, teacher.user_id)
    return MeOut(profile=ProfileOut.of(row or {}), user_id=teacher.user_id)


@router.post("/sync-profile", response_model=ProfileOut)
async def sync_profile(
    body: SyncProfileIn,
    request: Request,
    teacher: CurrentTeacher,
) -> ProfileOut:
    database = require_database(request)
    row = await profiles_repo.update_profile(
        database.pool,
        teacher.profile_id,
        full_name=body.full_name,
        department_ids=body.department_ids,
        subjects=body.subjects,
    )
    return ProfileOut.of(row or {})
