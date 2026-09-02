"""Apply Supabase/Postgres migrations in filename order.

Usage:
    python scripts/apply_migrations.py --dsn "$DATABASE_URL"
    # or with DATABASE_URL set in the environment / .env
    python scripts/apply_migrations.py

Each migration runs inside a transaction and is recorded in
public.schema_migrations so re-running is a no-op.
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

import asyncpg
from dotenv import load_dotenv

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"


async def apply(dsn: str, migrations_dir: pathlib.Path) -> None:
    files = sorted(migrations_dir.glob("*.sql"))
    if not files:
        print(f"No migrations found in {migrations_dir}")
        return

    connection: asyncpg.Connection = await asyncpg.connect(dsn, statement_cache_size=0)
    try:
        await connection.execute(
            """
            create table if not exists public.schema_migrations (
                name text primary key,
                applied_at timestamptz not null default now()
            )
            """
        )
        applied = {
            row["name"]
            for row in await connection.fetch("select name from public.schema_migrations")
        }
        for path in files:
            if path.name in applied:
                print(f"skip  {path.name} (already applied)")
                continue
            sql = path.read_text(encoding="utf-8")
            async with connection.transaction():
                await connection.execute(sql)
                await connection.execute(
                    "insert into public.schema_migrations(name) values ($1)", path.name
                )
            print(f"apply {path.name}")
    finally:
        await connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=None, help="Postgres DSN (defaults to $DIRECT_URL, then $DATABASE_URL)")
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env")
    import os

    dsn = (
        args.dsn
        or os.getenv("DIRECT_URL")
        or os.getenv("DATABASE_URL")
        or ""
    )
    if not dsn:
        print("ERROR: provide --dsn, DIRECT_URL or DATABASE_URL", file=sys.stderr)
        return 1
    try:
        asyncio.run(apply(dsn, MIGRATIONS_DIR))
    except asyncpg.PostgresError as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
