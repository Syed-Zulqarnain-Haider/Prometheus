"""End-to-end Alembic migration tests against a REAL Postgres over asyncpg.

The rest of the suite builds its schema with ``Base.metadata.create_all`` (fast, but it
NEVER exercises the migration files). That gap let a broken migration ship: the
``access_expires_at`` migration mixed bind-parameter styles in its FK-introspection query
(``:tbl::regclass`` — a named bind glued to a ``::`` cast), which asyncpg rejects with
``syntax error at or near ":"``. The column was never created and the auth path 500'd.

These tests run the actual ``alembic upgrade head`` / ``downgrade`` against the test
database over asyncpg, so a parameter-style regression in ANY migration fails CI here.
"""

import os
import subprocess
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import TEST_DATABASE_URL

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_HEAD = "b2c3d4e5f6a7"  # access_requests (current head)
_BEFORE_EXPIRY = "f4a1c9d2e7b3"  # revision just before the access_expires_at migration


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the alembic CLI against the TEST database over asyncpg (as CI/prod do)."""
    env = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=_BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )


@pytest_asyncio.fixture
async def clean_db() -> AsyncGenerator[None, None]:
    """Give each migration test a pristine schema, and leave one behind (other fixtures
    drop/recreate their own tables, but we don't want stray migration state to linger).

    The ``fact_daily_performance`` table is sync-owned (created by the sync DDL, not by
    Alembic) yet two migrations ALTER it, so we materialize it up front exactly as a real
    deploy would have it — otherwise the chain can't reach the migration under test."""
    from app.core.fact_table import fact_metadata

    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(fact_metadata.create_all)
    await engine.dispose()
    yield
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await engine.dispose()


async def _column_exists(table: str, column: str) -> bool:
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.connect() as conn:
            found = await conn.scalar(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = :c"
                ),
                {"t": table, "c": column},
            )
        return found == 1
    finally:
        await engine.dispose()


async def _fk_ondelete(table: str, column: str) -> str | None:
    """Return the FK's ON DELETE action code (confdeltype) for table.column -> users."""
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.connect() as conn:
            # confdeltype is a single-byte "char"; asyncpg surfaces it as bytes.
            raw = await conn.scalar(
                text(
                    """
                    SELECT con.confdeltype
                    FROM pg_constraint con
                    WHERE con.contype = 'f'
                      AND con.conrelid = CAST(:tbl AS regclass)
                      AND con.confrelid = CAST('users' AS regclass)
                      AND con.conkey = ARRAY[(
                          SELECT attnum FROM pg_attribute
                          WHERE attrelid = CAST(:tbl AS regclass)
                            AND attname = :col AND NOT attisdropped
                      )]
                    """
                ),
                {"tbl": table, "col": column},
            )
        if isinstance(raw, bytes):
            return raw.decode()
        return raw
    finally:
        await engine.dispose()


@pytest.mark.usefixtures("clean_db")
async def test_upgrade_head_applies_cleanly_over_asyncpg() -> None:
    """The full chain (including the access_expires_at FK-introspection migration and the
    chained access_requests migration) reaches head with no parameter-style syntax error."""
    result = _alembic("upgrade", "head")
    assert result.returncode == 0, f"alembic upgrade head failed:\n{result.stderr}"
    assert "syntax error" not in result.stderr.lower()

    # The column the auth path reads must now exist.
    assert await _column_exists("users", "access_expires_at")
    # And the FKs were recreated with the intended ON DELETE actions ('n' = SET NULL,
    # 'c' = CASCADE) — proving _recreate_user_fks actually ran, not just the add_column.
    assert await _fk_ondelete("audit_log", "user_id") == "n"
    assert await _fk_ondelete("report_shares", "shared_by") == "c"
    # The chained migration applied too (head == access_requests).
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.connect() as conn:
            version = await conn.scalar(text("SELECT version_num FROM alembic_version"))
    finally:
        await engine.dispose()
    assert version == _HEAD


@pytest.mark.usefixtures("clean_db")
async def test_downgrade_then_upgrade_roundtrips_over_asyncpg() -> None:
    """Downgrade exercises the SAME FK-introspection helper in reverse; the chain must then
    re-upgrade cleanly. A broken bind-style would fail in either direction."""
    assert _alembic("upgrade", "head").returncode == 0

    # Downgrade past the access_expires_at migration (runs its downgrade()).
    down = _alembic("downgrade", _BEFORE_EXPIRY)
    assert down.returncode == 0, f"downgrade failed:\n{down.stderr}"
    assert not await _column_exists("users", "access_expires_at")

    # Re-upgrade to head re-applies the whole tail.
    up = _alembic("upgrade", "head")
    assert up.returncode == 0, f"re-upgrade failed:\n{up.stderr}"
    assert await _column_exists("users", "access_expires_at")
