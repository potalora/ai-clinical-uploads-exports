"""TDD for W15 (HIPAA AUDIT-01, SEC-SUP-04): the ``audit_log`` table must be
append-only at the database level.

``audit_log`` is the HIPAA audit trail. As a plain table the application (or a
compromised app credential) can freely ``UPDATE``/``DELETE`` rows, so the trail
can be rewritten or erased with no trace. Migration
``a1b2c3d4e5f7_audit_log_append_only`` installs a ``BEFORE UPDATE OR DELETE``
trigger whose PL/pgSQL function ``RAISE EXCEPTION``s, so any attempt to modify or
remove an audit row fails at the DB layer regardless of the connecting role.

The trigger deliberately does NOT guard ``TRUNCATE`` — the test suite's conftest
TRUNCATEs ``audit_log`` between tests, and a TRUNCATE guard would break the whole
suite. (Append-only against the app's normal write path is what matters; a
TRUNCATE requires table-owner/elevated rights the app role should not hold —
see the migration docstring on the complementary INSERT-only DB role.)

These tests CREATE the trigger by executing the migration's SQL constants against
the test session's connection (the test DB is built by conftest ``create_all``,
which does not run migrations, so the trigger is otherwise absent). They then
assert: INSERT allowed, UPDATE blocked, DELETE blocked, TRUNCATE still allowed.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, InternalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

# A modification (UPDATE/DELETE) blocked by the PL/pgSQL ``RAISE EXCEPTION``
# surfaces through asyncpg as one of these SQLAlchemy DBAPI wrappers.
_BLOCKED = (InternalError, ProgrammingError, IntegrityError, DBAPIError)

# The Alembic ``versions`` dir is not an importable package (no ``__init__``),
# so load the migration module by file path to reuse its exact SQL constants.
_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "a1b2c3d4e5f7_audit_log_append_only.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "_w15_audit_append_only_migration", _MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _install_append_only_trigger(session: AsyncSession) -> None:
    """Install the W15 append-only trigger on ``audit_log`` for this test.

    Executes the exact ``upgrade`` SQL statements factored into the migration
    module as importable constants, then commits so the trigger is active for
    the subsequent INSERT/UPDATE/DELETE in the same session.
    """
    for stmt in _load_migration().UPGRADE_STATEMENTS:
        await session.execute(text(stmt))
    await session.commit()


async def _drop_append_only_trigger(session: AsyncSession) -> None:
    """Remove the trigger again (migration ``downgrade`` SQL) so the trigger
    does not leak onto the shared test DB for any later suite."""
    for stmt in _load_migration().DOWNGRADE_STATEMENTS:
        await session.execute(text(stmt))
    await session.commit()


async def _insert_audit_row(session: AsyncSession, action: str = "phi.read") -> None:
    """Insert one audit_log row (id + created_at carry server defaults)."""
    await session.execute(
        text("INSERT INTO audit_log (action) VALUES (:action)"),
        {"action": action},
    )
    await session.commit()


def _count_sql() -> str:
    return "SELECT count(*) FROM audit_log"


@pytest.mark.asyncio
async def test_insert_is_allowed(db_session: AsyncSession) -> None:
    """An INSERT (the only legitimate audit write) still succeeds with the
    trigger in place."""
    await _install_append_only_trigger(db_session)
    try:
        await _insert_audit_row(db_session, "phi.read")
        count = (await db_session.execute(text(_count_sql()))).scalar_one()
        assert count == 1
    finally:
        await db_session.rollback()
        await _drop_append_only_trigger(db_session)


@pytest.mark.asyncio
async def test_update_is_blocked(db_session: AsyncSession) -> None:
    """An UPDATE against audit_log is rejected by the trigger."""
    await _install_append_only_trigger(db_session)
    try:
        await _insert_audit_row(db_session, "phi.read")

        with pytest.raises(_BLOCKED):
            await db_session.execute(
                text("UPDATE audit_log SET action = 'tampered'")
            )
            await db_session.commit()
        await db_session.rollback()

        # The original row is untouched.
        action = (
            await db_session.execute(text("SELECT action FROM audit_log"))
        ).scalar_one()
        assert action == "phi.read"
    finally:
        await db_session.rollback()
        await _drop_append_only_trigger(db_session)


@pytest.mark.asyncio
async def test_delete_is_blocked(db_session: AsyncSession) -> None:
    """A DELETE against audit_log is rejected by the trigger."""
    await _install_append_only_trigger(db_session)
    try:
        await _insert_audit_row(db_session, "phi.read")

        with pytest.raises(_BLOCKED):
            await db_session.execute(text("DELETE FROM audit_log"))
            await db_session.commit()
        await db_session.rollback()

        # The row survives the blocked delete.
        count = (await db_session.execute(text(_count_sql()))).scalar_one()
        assert count == 1
    finally:
        await db_session.rollback()
        await _drop_append_only_trigger(db_session)


@pytest.mark.asyncio
async def test_truncate_is_still_allowed(db_session: AsyncSession) -> None:
    """TRUNCATE is intentionally NOT guarded so conftest cleanup keeps working."""
    await _install_append_only_trigger(db_session)
    try:
        await _insert_audit_row(db_session, "phi.read")

        await db_session.execute(text("TRUNCATE audit_log"))
        await db_session.commit()

        count = (await db_session.execute(text(_count_sql()))).scalar_one()
        assert count == 0
    finally:
        await db_session.rollback()
        await _drop_append_only_trigger(db_session)
