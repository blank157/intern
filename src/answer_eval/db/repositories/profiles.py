"""Profile repository: rows in public.profiles keyed by auth.users.id."""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg

_PROFILE_COLUMNS = "id, email, full_name, institution_id, role, department_ids, subjects"

_UNSET = object()


def _coerce_user_id(user_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(user_id))
    except ValueError as exc:
        raise ValueError(f"Invalid user id '{user_id}'") from exc


def _to_dict(row: asyncpg.Record | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    data["id"] = str(data["id"])
    if data.get("institution_id") is not None:
        data["institution_id"] = str(data["institution_id"])
    data["department_ids"] = _as_str_list(data.get("department_ids"))
    data["subjects"] = _as_str_list(data.get("subjects"))
    return data


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except ValueError:
            return []
        return [str(item) for item in decoded] if isinstance(decoded, list) else []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return []


async def ensure_profile(
    pool: asyncpg.Pool,
    *,
    user_id: str,
    email: str,
    full_name: str = "",
    department_ids: list[str] | None = None,
    subjects: list[str] | None = None,
) -> dict[str, Any]:
    """Insert the profile on first login; backfill empty fields from claims."""
    query = f"""
        insert into profiles (id, email, full_name, department_ids, subjects)
        values ($1, $2, $3, $4, $5)
        on conflict (id) do update set
            email = excluded.email,
            full_name = case when profiles.full_name = '' then excluded.full_name
                             else profiles.full_name end,
            department_ids = case when profiles.department_ids = '[]'::jsonb
                                  then excluded.department_ids
                                  else profiles.department_ids end,
            subjects = case when profiles.subjects = '[]'::jsonb
                            then excluded.subjects
                            else profiles.subjects end
        returning {_PROFILE_COLUMNS}
    """
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            query,
            _coerce_user_id(user_id),
            email or "",
            full_name or "",
            department_ids or [],
            subjects or [],
        )
    result = _to_dict(row)
    assert result is not None
    return result


async def get_profile(pool: asyncpg.Pool, user_id: str) -> dict[str, Any] | None:
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            f"select {_PROFILE_COLUMNS} from profiles where id = $1",
            _coerce_user_id(user_id),
        )
    return _to_dict(row)


async def update_profile(
    pool: asyncpg.Pool,
    user_id: str,
    *,
    full_name: str | None = None,
    department_ids: list[str] | None = None,
    subjects: list[str] | None = None,
    institution_id: Any = _UNSET,
) -> dict[str, Any] | None:
    assignments: list[str] = []
    values: list[Any] = [_coerce_user_id(user_id)]
    placeholder = 2

    if full_name is not None:
        assignments.append(f"full_name = ${placeholder}")
        values.append(full_name)
        placeholder += 1
    if department_ids is not None:
        assignments.append(f"department_ids = ${placeholder}")
        values.append(department_ids)
        placeholder += 1
    if subjects is not None:
        assignments.append(f"subjects = ${placeholder}")
        values.append(subjects)
        placeholder += 1
    if institution_id is not _UNSET:
        assignments.append(
            f"institution_id = ${placeholder}::uuid"
            if institution_id
            else "institution_id = null"
        )
        if institution_id:
            values.append(uuid.UUID(institution_id))
            placeholder += 1

    if not assignments:
        return await get_profile(pool, user_id)

    query = (
        f"update profiles set {', '.join(assignments)}, updated_at = now() "
        f"where id = $1 returning {_PROFILE_COLUMNS}"
    )
    async with pool.acquire() as connection:
        row = await connection.fetchrow(query, *values)
    return _to_dict(row)


def _json_list(items: list[str]) -> str:
    import json

    return json.dumps(list(items))
