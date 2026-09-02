"""One-off admin helper: enqueue durable evaluation jobs for an assessment's
queued submissions.

Single-node bridge (no Redis needed):
  - builds rubrics + teacher rules from the frozen resolved policies,
  - flips each submission with status=queued into a durable Postgres job,
  - prints a summary. The evaluation worker then claims those jobs.

Usage:
    python scripts/enqueue_assessment.py <assessment_id> [--database DSN] [--storage-root PATH]

Defaults come from env (DATABASE_URL/DIRECT_URL, STORAGE_LOCAL_ROOT=data/storage).
Idempotent: submissions that already have an active job are skipped.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assessment_id")
    parser.add_argument("--database", default=None, help="Durable job store DSN")
    parser.add_argument("--storage-root", default=None, help="Local storage root (default STORAGE_LOCAL_ROOT=data/storage)")
    args = parser.parse_args()

    load_dotenv()
    dsn = args.database or os.getenv("DATABASE_URL") or os.getenv("DIRECT_URL")
    if not dsn:
        print("[enqueue] --database or DATABASE_URL/DIRECT_URL is required", file=sys.stderr)
        return 2
    storage_root = Path(args.storage_root or os.getenv("STORAGE_LOCAL_ROOT", "data/storage"))

    import asyncio

    import asyncpg

    from answer_eval.db.repositories import policies as policies_repo
    from answer_eval.db.repositories import submissions as submissions_repo
    from answer_eval.grading.hydrate import build_workflow_inputs
    from answer_eval.jobs import PostgresJobStore
    from answer_eval.jobs.queue import create_queue
    from answer_eval.jobs.service import EvaluationJobService

    async def run() -> int:
        conn = await asyncpg.connect(dsn, statement_cache_size=0)
        try:
            resolved = await policies_repo.get_resolved(conn, assessment_id=args.assessment_id)
            if not resolved:
                print(f"[enqueue] assessment {args.assessment_id}: no resolved policies (finalize first)")
                return 1
            rubrics, teacher_rules = build_workflow_inputs(resolved)
            print(f"[enqueue] resolved policies -> {len(rubrics)} rubric(s): {', '.join(rubrics)}")

            roster = await submissions_repo.list_for_assessment(conn, assessment_id=args.assessment_id)
            queued = [s for s in roster if s["status"] == "queued"]
            print(f"[enqueue] submissions: {len(roster)} total, {len(queued)} queued")
        finally:
            await conn.close()

        store = PostgresJobStore(dsn)
        try:
            service = EvaluationJobService(store, create_queue(None))
            created = 0
            skipped = 0
            for item in queued:
                object_key = item.get("pdf_object_key")
                if not object_key:
                    print(f"[enqueue] skip {item['roll_number']}: no stored PDF")
                    skipped += 1
                    continue
                pdf_path = str(storage_root / object_key)
                if not Path(pdf_path).is_file():
                    print(f"[enqueue] skip {item['roll_number']}: PDF missing at {pdf_path}")
                    skipped += 1
                    continue
                _, ok = service.submit(
                    submission_id=item["id"],
                    pdf_path=pdf_path,
                    rubrics=rubrics,
                    teacher_rules=teacher_rules,
                )
                created += 1 if ok else 0
                skipped += 0 if ok else 1
                print(f"[enqueue] {'enqueued' if ok else 'already-active'} {item['roll_number']}")
        finally:
            store.close()

        print(f"[enqueue] done: {created} created, {skipped} already-active/skipped")
        print("[enqueue] start a worker to consume them, e.g.:")
        print(f"  python -m answer_eval.jobs.worker_main --coordinator http://127.0.0.1:8300 --database {dsn}")
        return 0

    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
