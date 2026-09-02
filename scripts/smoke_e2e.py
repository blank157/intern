"""Live end-to-end smoke: Supabase auth -> FastAPI -> Supabase Postgres.

Prerequisites:
    * .env contains SUPABASE_*, DATABASE_URL (transaction pooler)
    * migrations applied (scripts/apply_migrations.py)
    * smoke user exists (created once via admin API)

Usage:
    python scripts/smoke_e2e.py [--base-url http://127.0.0.1:8300]

Checks:
    1. GET  /api/healthz                     -> database connected
    2. POST /auth/v1/token (Supabase)        -> real JWT for smoke teacher
    3. GET  /api/auth/me with JWT            -> profile auto-provisioned
    4. PATCH /api/profile                    -> subjects persisted
    5. GET  /api/auth/me again               -> updated values returned
    6. GET  {SUPABASE_URL}/rest/v1/assessments with ANON key only
                                             -> RLS blocks (empty list)
"""

from __future__ import annotations

import argparse
import os
import sys

import httpx
from dotenv import load_dotenv

SMOKE_EMAIL = "evalai-smoke@test.evalai.local"
SMOKE_PASSWORD = "EvalAI-Smoke-2026!"
SMOKE_PASSWORD_ENV = "SMOKE_USER_PASSWORD"


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"{'PASS' if ok else 'FAIL'}  {name}{(' — ' + detail) if detail else ''}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8300")
    args = parser.parse_args()

    load_dotenv()
    supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
    anon_key = os.environ["SUPABASE_ANON_KEY"]
    password = os.environ.get(SMOKE_PASSWORD_ENV) or SMOKE_PASSWORD

    client = httpx.Client(timeout=30.0)
    all_ok = True

    # 1. Health
    response = client.get(f"{args.base_url}/api/healthz")
    body = response.json()
    all_ok &= check("healthz", response.status_code == 200 and body.get("database") is True, str(body))
    request_id = response.headers.get("X-Request-ID")
    all_ok &= check("request-id header present", bool(request_id), str(request_id))

    # 2. Real Supabase login
    auth_response = client.post(
        f"{supabase_url}/auth/v1/token?grant_type=password",
        headers={"apikey": anon_key, "Content-Type": "application/json"},
        json={"email": SMOKE_EMAIL, "password": password},
    )
    token = auth_response.json().get("access_token")
    all_ok &= check("supabase password grant", auth_response.status_code == 200 and bool(token))

    headers = {"Authorization": f"Bearer {token}"}

    # 3. /auth/me provisions + returns profile
    response = client.get(f"{args.base_url}/api/auth/me", headers=headers)
    profile = response.json().get("profile", {})
    all_ok &= check(
        "auth/me profile provisioned",
        response.status_code == 200 and profile.get("email") == SMOKE_EMAIL,
        f"name={profile.get('full_name')!r} departments={profile.get('department_ids')}",
    )

    # 4. PATCH /profile persists
    new_subjects = ["Machine Learning", "DBMS"]
    response = client.patch(
        f"{args.base_url}/api/profile",
        headers=headers,
        json={"subjects": new_subjects},
    )
    all_ok &= check(
        "patch profile",
        response.status_code == 200 and response.json().get("subjects") == new_subjects,
        str(response.json().get("subjects")),
    )

    # 5. Values round-trip
    response = client.get(f"{args.base_url}/api/auth/me", headers=headers)
    all_ok &= check(
        "profile round-trip",
        response.json().get("profile", {}).get("subjects") == new_subjects,
    )

    # 6. RLS: anon key sees no assessments rows
    rest_response = client.get(
        f"{supabase_url}/rest/v1/assessments?select=id",
        headers={"apikey": anon_key},
    )
    all_ok &= check(
        "RLS blocks anon reads of assessments",
        rest_response.status_code == 200 and rest_response.json() == [],
        f"status={rest_response.status_code} body={rest_response.text[:80]}",
    )

    # 7. Unauthenticated API access is rejected
    response = client.get(f"{args.base_url}/api/profile")
    all_ok &= check(
        "unauthenticated /api/profile rejected",
        response.status_code == 401,
        str(response.json()),
    )

    print("\nRESULT:", "ALL PASS" if all_ok else "FAILURES DETECTED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
