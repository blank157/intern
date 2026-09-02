"""Milestone 3 HTTP smoke against a RUNNING API server (default :8300).

Usage:
    python scripts/smoke_m3_http.py [--base-url http://127.0.0.1:8300]
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import zipfile

import fitz
import httpx
from dotenv import load_dotenv

EMAIL = "evalai-smoke@test.evalai.local"
PASSWORD = "EvalAI-Smoke-2026!"


def make_pdf(text: str) -> bytes:
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), text)
    return doc.tobytes()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8300")
    args = parser.parse_args()

    load_dotenv()
    supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
    anon_key = os.environ["SUPABASE_ANON_KEY"]
    client = httpx.Client(timeout=60)

    login = client.post(
        f"{supabase_url}/auth/v1/token?grant_type=password",
        headers={"apikey": anon_key},
        json={"email": EMAIL, "password": PASSWORD},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(f"{args.base_url}/api/assessments", headers=headers, json={})
    assert created.status_code == 201, created.text
    assessment_id = created.json()["assessment"]["id"]

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("24HT001.pdf", make_pdf("HTTP smoke paper 1"))
        archive.writestr("24HT002.pdf", make_pdf("HTTP smoke paper 2"))
        archive.writestr("broken.pdf", b"junk")
        archive.writestr("notes.txt", b"skip")
    buffer.seek(0)

    upload = client.post(
        f"{args.base_url}/api/assessments/{assessment_id}/student-zip",
        headers=headers,
        files={"file": ("papers.zip", buffer.getvalue(), "application/zip")},
    )
    result = upload.json()
    ok = (
        upload.status_code == 200
        and result["detected"] == 4
        and result["valid"] == 2
        and result["invalid"] == 2
    )
    print(("PASS" if ok else "FAIL"), "upload:", {k: result[k] for k in ("detected", "valid", "invalid")})

    roster = client.get(f"{args.base_url}/api/assessments/{assessment_id}/students", headers=headers)
    rolls = sorted(item["roll_number"] for item in roster.json())
    ok &= roster.status_code == 200 and rolls == ["24HT001", "24HT002"]
    print(("PASS" if ok else "FAIL"), "roster:", rolls)

    deleted = client.delete(f"{args.base_url}/api/assessments/{assessment_id}", headers=headers)
    ok &= deleted.status_code == 200
    print(("PASS" if ok else "FAIL"), "cleanup delete")
    print("RESULT:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
