"""Runtime guard for the single supported product database schema."""

from __future__ import annotations

from typing import Any


CURRENT_SCHEMA_REVISION = "20260803_0012"


class SchemaVersionError(RuntimeError):
    """Sanitized startup failure for an unavailable or stale schema."""


def require_current_schema(connection: Any) -> None:
    """Require the one Alembic head understood by this product build."""

    try:
        rows = connection.execute(
            "SELECT version_num FROM halpha_meta.alembic_version"
        ).fetchall()
    except Exception:
        raise SchemaVersionError("DATABASE_SCHEMA_VERSION_UNAVAILABLE") from None
    actual = tuple(str(row[0]) for row in rows)
    if actual != (CURRENT_SCHEMA_REVISION,):
        actual_label = actual[0] if len(actual) == 1 else "INVALID"
        raise SchemaVersionError(
            "DATABASE_SCHEMA_VERSION_MISMATCH "
            f"expected={CURRENT_SCHEMA_REVISION} actual={actual_label}"
        )
