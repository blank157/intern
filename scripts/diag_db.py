"""Diagnose asyncpg connectivity to both pooler modes."""

from __future__ import annotations

import asyncio
import os

import asyncpg
from dotenv import load_dotenv


async def try_connect(label: str, dsn: str) -> None:
    print(f"--- {label} ---")
    try:
        conn = await asyncio.wait_for(
            asyncpg.connect(dsn, statement_cache_size=0, timeout=15),
            timeout=20,
        )
        value = await conn.fetchval("select version()")
        print("OK:", value[:60])
        await conn.close()
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED ({type(exc).__name__}): {exc}")


async def main() -> None:
    load_dotenv()
    base = os.environ["DATABASE_URL"]
    direct = os.environ.get("DIRECT_URL", "")
    await try_connect("transaction pooler (as-is)", base)
    await try_connect("transaction pooler (sslmode=require)", base + ("&" if "?" in base else "?") + "sslmode=require")
    if direct:
        await try_connect("session mode (as-is)", direct)


asyncio.run(main())
