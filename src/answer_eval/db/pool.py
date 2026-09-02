"""Asyncpg connection pool lifecycle for the EvalAI control plane."""

from __future__ import annotations

import json
import logging
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import asyncpg

logger = logging.getLogger(__name__)

# Pooler-specific query params that asyncpg would reject as startup parameters.
_NONSTANDARD_QUERY_PARAMS = {"pgbouncer", "connection_limit", "pool_timeout"}


def sanitize_dsn(dsn: str) -> str:
    """Drop non-Postgres query params (e.g. Supabase's ?pgbouncer=true)."""
    try:
        parts = urlsplit(dsn)
    except ValueError:
        return dsn
    if not parts.query:
        return dsn
    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _NONSTANDARD_QUERY_PARAMS
    ]
    if len(kept) == len(parse_qsl(parts.query, keep_blank_values=True)):
        return dsn
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment))


async def _init_connection(connection: asyncpg.Connection) -> None:
    """Decode json/jsonb into Python objects instead of raw strings."""
    await connection.set_type_codec(
        "json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )
    await connection.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


class Database:
    """Thin wrapper around an asyncpg pool.

    `statement_cache_size=0` keeps the pool compatible with pgbouncer/Supavisor
    transaction pooling; it is harmless on direct connections.
    """

    def __init__(self, dsn: str, *, min_size: int = 0, max_size: int = 10) -> None:
        self._dsn = sanitize_dsn(dsn)
        self._min_size = min_size
        self._max_size = max_size
        self._pool: asyncpg.Pool | None = None

    @property
    def connected(self) -> bool:
        return self._pool is not None

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Database pool is not connected")
        return self._pool

    async def connect(self) -> None:
        if self._pool is not None:
            return
        logger.info("Connecting to application database")
        self._pool = await asyncpg.create_pool(
            self._dsn,
            min_size=self._min_size,
            max_size=self._max_size,
            statement_cache_size=0,
            command_timeout=60,
            init=_init_connection,
        )

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
