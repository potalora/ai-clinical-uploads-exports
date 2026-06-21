"""Make audit_log append-only at the DB level (W15 / HIPAA AUDIT-01, SEC-SUP-04).

The HIPAA audit trail lives in ``audit_log``. As an ordinary table, the
application credential can freely ``UPDATE`` or ``DELETE`` rows, so the trail can
be silently rewritten or erased — defeating its purpose as tamper-evidence. This
migration installs a ``BEFORE UPDATE OR DELETE`` trigger whose PL/pgSQL function
``RAISE EXCEPTION``s, so any attempt to modify or remove an existing audit row
fails at the database layer, no matter which role issues it.

Scope of the guard — UPDATE and DELETE ONLY. ``INSERT`` (the one legitimate audit
write) is untouched, and ``TRUNCATE`` is deliberately NOT guarded:

  * Append-only against the application's normal write path is the goal; the app
    only ever INSERTs audit rows.
  * The test suite's conftest TRUNCATEs ``audit_log`` between tests for cleanup; a
    ``BEFORE TRUNCATE`` trigger would break the entire suite.
  * TRUNCATE already requires table-owner / elevated privileges that the runtime
    app role should not be granted.

Defense-in-depth (deployment hardening, NOT implemented here — it lives in the
container/infra layer owned elsewhere): run the application under a dedicated DB
role that has ``INSERT`` but NOT ``UPDATE``/``DELETE``/``TRUNCATE`` on
``audit_log`` (e.g. ``GRANT INSERT ON audit_log TO app_rw; REVOKE UPDATE, DELETE,
TRUNCATE ON audit_log FROM app_rw;``). The trigger enforces append-only
regardless of role; the least-privilege role is a second, independent layer.

The trigger function and trigger are statement-level (``FOR EACH STATEMENT``) so
even a zero-row ``DELETE FROM audit_log WHERE false`` is rejected, and the SQL is
factored into the importable ``UPGRADE_STATEMENTS`` / ``DOWNGRADE_STATEMENTS``
constants so the test can install and exercise the same statements against the
``create_all``-built test DB (which does not run migrations).

Revision ID: a1b2c3d4e5f7
Revises: c4d5e6f7a8b9
Create Date: 2026-06-21
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f7"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


_FUNCTION_NAME = "audit_log_prevent_modification"
_TRIGGER_NAME = "audit_log_append_only"

# The PL/pgSQL guard. The message carries only the operation (``TG_OP``) — never
# row data — so it is PHI-safe to surface/log. Default errcode is P0001
# (raise_exception), which asyncpg/SQLAlchemy wrap as a DBAPI error.
_CREATE_FUNCTION = f"""
CREATE OR REPLACE FUNCTION {_FUNCTION_NAME}()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'audit_log is append-only: % is not permitted (W15 / HIPAA AUDIT-01)',
        TG_OP;
END;
$$;
""".strip()

_CREATE_TRIGGER = f"""
CREATE TRIGGER {_TRIGGER_NAME}
BEFORE UPDATE OR DELETE ON audit_log
FOR EACH STATEMENT
EXECUTE FUNCTION {_FUNCTION_NAME}();
""".strip()

_DROP_TRIGGER = f"DROP TRIGGER IF EXISTS {_TRIGGER_NAME} ON audit_log;"
_DROP_FUNCTION = f"DROP FUNCTION IF EXISTS {_FUNCTION_NAME}();"

# Importable, ordered statement lists. ``upgrade``/``downgrade`` run these, and
# the test installs/removes the trigger by executing the very same SQL.
# ``DROP TRIGGER IF EXISTS`` precedes the CREATE so re-installs are idempotent.
UPGRADE_STATEMENTS: tuple[str, ...] = (
    _CREATE_FUNCTION,
    _DROP_TRIGGER,
    _CREATE_TRIGGER,
)

DOWNGRADE_STATEMENTS: tuple[str, ...] = (
    _DROP_TRIGGER,
    _DROP_FUNCTION,
)


def upgrade() -> None:
    for stmt in UPGRADE_STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE_STATEMENTS:
        op.execute(stmt)
