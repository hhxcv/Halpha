"""Alembic environment that accepts only an in-memory authenticated connection."""

from __future__ import annotations

from alembic import context
from sqlalchemy import text


config = context.config
connection = config.attributes.get("connection")
if connection is None:
    raise RuntimeError("MIGRATION_CONNECTION_ATTRIBUTE_REQUIRED")

connection.execute(text("CREATE SCHEMA IF NOT EXISTS halpha_meta AUTHORIZATION CURRENT_USER"))
connection.commit()
context.configure(
    connection=connection,
    target_metadata=None,
    transactional_ddl=True,
    compare_type=True,
    version_table="alembic_version",
    version_table_schema="halpha_meta",
)

with context.begin_transaction():
    context.run_migrations()
