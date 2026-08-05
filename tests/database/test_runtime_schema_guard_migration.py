from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "migrations"
    / "versions"
    / "20260731_0010_runtime_schema_guard.py"
)


def _revision_module():
    spec = importlib.util.spec_from_file_location(
        "halpha_runtime_schema_guard",
        MIGRATION,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("database_name", "expected"),
    (
        ("halpha_demo", ("halpha_demo", False)),
        ("halpha_live", ("halpha_live", True)),
        ("halpha_live_copy", ("halpha_live_copy", True)),
        ("halpha_live_personal", ("halpha_live_personal", True)),
        ("halpha_workbench_fixture_12", ("halpha_demo", False)),
    ),
)
def test_runtime_schema_guard_resolves_only_supported_databases(
    monkeypatch,
    database_name: str,
    expected: tuple[str, bool],
) -> None:
    revision = _revision_module()

    class Result:
        @staticmethod
        def scalar_one():
            return database_name

    class Connection:
        @staticmethod
        def execute(_query):
            return Result()

    monkeypatch.setattr(revision.op, "get_bind", lambda: Connection())

    assert revision._role_prefix() == expected


def test_runtime_schema_guard_rejects_unrelated_database(monkeypatch) -> None:
    revision = _revision_module()

    class Result:
        @staticmethod
        def scalar_one():
            return "postgres"

    class Connection:
        @staticmethod
        def execute(_query):
            return Result()

    monkeypatch.setattr(revision.op, "get_bind", lambda: Connection())

    with pytest.raises(RuntimeError, match="UNSUPPORTED_HALPHA_DATABASE"):
        revision._role_prefix()


@pytest.mark.parametrize(
    ("role_prefix", "is_live", "expected_roles"),
    (
        (
            "halpha_demo",
            False,
            {"halpha_demo_app", "halpha_demo_executor"},
        ),
        (
            "halpha_live",
            True,
            {
                "halpha_live_app",
                "halpha_live_app_reader",
                "halpha_live_executor",
            },
        ),
        (
            "halpha_live_copy",
            True,
            {
                "halpha_live_copy_app",
                "halpha_live_copy_app_reader",
                "halpha_live_copy_executor",
            },
        ),
        (
            "halpha_live_personal",
            True,
            {
                "halpha_live_personal_app",
                "halpha_live_personal_app_reader",
                "halpha_live_personal_executor",
            },
        ),
    ),
)
def test_upgrade_grants_schema_read_to_runtime_roles_and_receipt_update(
    monkeypatch,
    role_prefix: str,
    is_live: bool,
    expected_roles: set[str],
) -> None:
    revision = _revision_module()
    statements: list[str] = []
    monkeypatch.setattr(revision, "_role_prefix", lambda: (role_prefix, is_live))
    monkeypatch.setattr(
        revision.op,
        "execute",
        lambda statement: statements.append(str(statement)),
    )

    revision.upgrade()

    for role in expected_roles:
        assert any(
            "GRANT USAGE ON SCHEMA halpha_meta" in statement and role in statement
            for statement in statements
        )
        assert any(
            "GRANT SELECT ON TABLE halpha_meta.alembic_version" in statement
            and role in statement
            for statement in statements
        )
    assert any(
        "GRANT UPDATE ON TABLE halpha.receipt" in statement
        and f"{role_prefix}_executor" in statement
        for statement in statements
    )
