"""One-off live verification of schema + RLS state (safe to delete)."""

from __future__ import annotations

import asyncio
import os

import asyncpg
from dotenv import load_dotenv


async def main() -> None:
    load_dotenv()
    conn = await asyncpg.connect(os.environ["DIRECT_URL"], statement_cache_size=0)  # type: ignore[arg-type]
    tables = await conn.fetch(
        "select tablename, rowsecurity from pg_tables where schemaname='public' order by tablename"
    )
    print(f"tables in public: {len(tables)}")
    rls_on = [t["tablename"] for t in tables if t["rowsecurity"]]
    rls_off = [t["tablename"] for t in tables if not t["rowsecurity"]]
    print("RLS enabled:", len(rls_on), "| RLS disabled:", rls_off or "none")
    policies = await conn.fetch("select count(*) as n from pg_policies where schemaname='public'")
    print("policies:", policies[0]["n"])
    cols = await conn.fetch(
        """select column_name from information_schema.columns
           where table_schema='public' and table_name='assessments'
           order by ordinal_position"""
    )
    print("assessments columns:", [c["column_name"] for c in cols][:10], "...")
    helpers = await conn.fetch(
        """select proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace
           where n.nspname='public' and proname in ('current_teacher_id','can_access_assessment','touch_updated_at')"""
    )
    print("helper functions:", sorted(h["proname"] for h in helpers))
    await conn.close()


asyncio.run(main())
