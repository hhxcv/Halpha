from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import psycopg
from psycopg import sql
import pytest

from halpha.database.record_families import PRODUCT_RECORD_FAMILIES
from halpha.database.schema_version import CURRENT_SCHEMA_REVISION
from halpha.database.security_contract import (
    AUTHORITY_CONSTRAINT_TABLES,
    AUTHORITY_PAIR_EXPRESSION,
    CRITICAL_TRIGGER_FUNCTIONS,
    DATABASE_ENVIRONMENT_CONSTRAINT_TABLES,
    LIVE_ACTIVATION_SAFETY_INDEX_PREDICATE,
)
from tools.provisioning.provision_halpha_databases import (
    ROLE_KINDS_BY_ENVIRONMENT,
    ROLE_SECURITY_ATTRIBUTES,
    _converge_database_acl,
    _converge_role,
    _database_access_roles,
    _managed_role_names,
    _revoke_managed_role_memberships,
    main as provision_databases_main,
)
from tools.qualification import verify_database_boundary


ROOT = Path(__file__).resolve().parents[2]
INSTALL = ROOT / "tools" / "provisioning" / "install_postgresql_17.ps1"
CONFIGURE = ROOT / "tools" / "provisioning" / "configure_postgresql_17.ps1"


def test_database_qualification_requires_the_fresh_baseline_head() -> None:
    assert verify_database_boundary.HEAD == CURRENT_SCHEMA_REVISION


def test_database_qualification_rejects_unknown_or_overloaded_halpha_functions() -> None:
    migration_role = "halpha_live_copy_migration"
    signatures = {
        f"{contract['function']}()"
        for contract in CRITICAL_TRIGGER_FUNCTIONS.values()
    }

    class _Rows:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

    class _FunctionConnection:
        def __init__(self, owners, acl):
            self._results = [owners, acl]

        def execute(self, _statement):
            return _Rows(self._results.pop(0))

    expected_owners = [(signature, migration_role) for signature in signatures]
    expected_acl = [
        (signature, migration_role, "EXECUTE", False)
        for signature in signatures
    ]
    exact = verify_database_boundary._inspect_function_boundary(
        _FunctionConnection(expected_owners, expected_acl),  # type: ignore[arg-type]
        "live_copy",
    )
    assert exact["function_owners"]["exact"] is True
    assert exact["function_acl"]["exact"] is True

    unexpected_signature = "unsafe_helper(text)"
    drift = verify_database_boundary._inspect_function_boundary(
        _FunctionConnection(
            [*expected_owners, (unexpected_signature, migration_role)],
            [
                *expected_acl,
                (unexpected_signature, "PUBLIC", "EXECUTE", False),
                (unexpected_signature, migration_role, "EXECUTE", False),
            ],
        ),  # type: ignore[arg-type]
        "live_copy",
    )
    assert drift["function_owners"]["exact"] is False
    assert drift["function_acl"]["exact"] is False
    assert drift["function_owners"]["unexpected"] == [
        [unexpected_signature, migration_role]
    ]


def test_install_secret_never_enters_process_arguments() -> None:
    source = INSTALL.read_text(encoding="utf-8").lower()
    assert "--pwfile" in source
    assert "--superpassword" not in source
    assert "--servicepassword" not in source


def test_psql_uses_only_a_temporary_pgpass_reference() -> None:
    source = CONFIGURE.read_text(encoding="utf-8")
    assert "$env:PGPASSFILE = $passFile" in source
    assert "--no-password" in source
    assert "Remove-Item Env:PGPASSFILE" in source
    assert "Remove-Item -LiteralPath $passFile -Force" in source
    assert "PGPASSWORD" not in source


def test_database_access_roles_revoke_every_peer_role_before_granting_own_roles() -> None:
    demo_granted, demo_revoked = _database_access_roles("demo")
    copy_granted, copy_revoked = _database_access_roles("live_copy")
    personal_granted, personal_revoked = _database_access_roles("live_personal")

    assert demo_granted == tuple(
        f"halpha_demo_{kind}" for kind in ROLE_KINDS_BY_ENVIRONMENT["demo"]
    )
    assert demo_revoked == tuple(
        f"halpha_{environment}_{kind}"
        for environment in ("live_copy", "live_personal")
        for kind in ROLE_KINDS_BY_ENVIRONMENT[environment]
    )
    assert copy_granted == tuple(
        f"halpha_live_copy_{kind}"
        for kind in ROLE_KINDS_BY_ENVIRONMENT["live_copy"]
    )
    assert set(copy_revoked) == set((*demo_granted, *personal_granted))
    assert set(personal_revoked) == set((*demo_granted, *copy_granted))
    assert "halpha_live_copy_app_reader" in copy_granted
    assert "halpha_demo_app_reader" not in demo_granted


def test_database_provisioning_removes_public_temporary_table_capability() -> None:
    source = (
        ROOT
        / "tools"
        / "provisioning"
        / "provision_halpha_databases.py"
    ).read_text(encoding="utf-8")

    assert "REVOKE ALL PRIVILEGES ON DATABASE {} FROM {}" in source
    assert "_converge_database_acl(" in source


class _RecordingCursor:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.calls: list[tuple[str, object | None]] = []

    def execute(self, statement, params=None):
        rendered = (
            statement.as_string()
            if isinstance(statement, sql.Composable)
            else str(statement)
        )
        self.calls.append((rendered, params))
        return self

    def fetchall(self):
        return list(self.rows)


@pytest.mark.parametrize(
    ("exists", "verb"),
    ((False, "CREATE ROLE"), (True, "ALTER ROLE")),
)
def test_database_provisioning_converges_every_security_attribute_and_resets_config(
    exists: bool,
    verb: str,
) -> None:
    cursor = _RecordingCursor()

    _converge_role(
        cursor,
        role="halpha_demo_app",
        role_secret="test-only-secret",
        exists=exists,
    )

    assert cursor.calls[0][0].startswith(f'{verb} "halpha_demo_app"')
    assert ROLE_SECURITY_ATTRIBUTES in cursor.calls[0][0]
    assert cursor.calls[1] == (
        'ALTER ROLE "halpha_demo_app" RESET ALL',
        None,
    )


def test_database_provisioning_revokes_all_membership_edges_touching_managed_roles() -> None:
    cursor = _RecordingCursor(
        rows=(
            ("external_admin", "halpha_demo_app"),
            ("halpha_live_copy_executor", "external_operator"),
            ("halpha_live_copy_executor", "external_operator"),
        )
    )

    _revoke_managed_role_memberships(cursor, _managed_role_names())

    assert cursor.calls[0][1] == (
        list(_managed_role_names()),
        list(_managed_role_names()),
    )
    assert [call[0] for call in cursor.calls[1:]] == [
        'REVOKE "external_admin" FROM "halpha_demo_app"',
        'REVOKE "halpha_live_copy_executor" FROM "external_operator"',
    ]


def test_database_acl_convergence_revokes_unknown_and_extra_privileges() -> None:
    cursor = _RecordingCursor(
        rows=(
            ("PUBLIC",),
            ("unexpected_role",),
            ("halpha_demo_app",),
            ("halpha_demo_migration",),
        )
    )
    granted, _ = _database_access_roles("demo")

    _converge_database_acl(
        cursor,
        database="halpha_demo",
        owner="halpha_demo_migration",
        granted_roles=granted,
    )

    statements = [call[0] for call in cursor.calls]
    assert any(
        statement
        == 'REVOKE ALL PRIVILEGES ON DATABASE "halpha_demo" FROM PUBLIC'
        for statement in statements
    )
    assert any(
        statement
        == 'REVOKE ALL PRIVILEGES ON DATABASE "halpha_demo" FROM "unexpected_role"'
        for statement in statements
    )
    assert not any(
        statement.endswith('FROM "halpha_demo_migration"')
        for statement in statements
    )
    assert {
        statement
        for statement in statements
        if statement.startswith("GRANT CONNECT")
    } == {
        f'GRANT CONNECT ON DATABASE "halpha_demo" TO "{role}"'
        for role in granted
    }


def test_database_provisioning_help_stops_before_runtime_or_secret_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tools.provisioning.provision_halpha_databases.require_repository_runtime",
        lambda: pytest.fail("help must stop before runtime validation"),
    )

    with pytest.raises(SystemExit) as exc_info:
        provision_databases_main(["--help"])

    assert exc_info.value.code == 0


def test_database_provisioning_rejects_unknown_arguments_before_secret_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tools.provisioning.provision_halpha_databases.require_repository_runtime",
        lambda: pytest.fail("unknown arguments must stop before runtime validation"),
    )

    with pytest.raises(SystemExit) as exc_info:
        provision_databases_main(["--reset-everything"])

    assert exc_info.value.code == 2


def test_cross_database_qualification_checks_all_roles_in_both_directions(
    monkeypatch,
) -> None:
    attempts: list[tuple[str, str, str]] = []

    def reject_cross_database(environment: str, role: str, *, database: str):
        attempts.append((environment, role, database))
        raise psycopg.OperationalError("permission denied for database")

    monkeypatch.setattr(
        verify_database_boundary,
        "_connect",
        reject_cross_database,
    )

    matrix = verify_database_boundary._cross_database_connect_matrix()

    expected_attempts = [
        (source, role, verify_database_boundary.ENVIRONMENTS[target]["database"])
        for source in verify_database_boundary.ENVIRONMENTS
        for target in verify_database_boundary.ENVIRONMENTS
        if source != target
        for role in ROLE_KINDS_BY_ENVIRONMENT[source]
    ]
    assert len(matrix) == len(expected_attempts)
    assert all(matrix.values())
    assert attempts == expected_attempts


def _qualified_environment(environment: str) -> dict:
    kind = "DEMO" if environment == "demo" else "LIVE"
    constraints = {
        name: {
            "table": table,
            "type": "c",
            "validated": True,
            "expression": AUTHORITY_PAIR_EXPRESSION,
        }
        for name, table in AUTHORITY_CONSTRAINT_TABLES.items()
    }
    constraints.update(
        {
            name: {
                "table": table,
                "type": "c",
                "validated": True,
                "expression": (
                    f"environment_kind::text = '{kind}'::text"
                ),
            }
            for name, table in DATABASE_ENVIRONMENT_CONSTRAINT_TABLES.items()
        }
    )
    triggers = {
        name: {
            "table": contract["table"],
            "enabled": "O",
            "type_bits": 27,
            "function": contract["function"],
            "body_sha256": contract["body_sha256"],
            "language": "plpgsql",
            "security_definer": False,
            "volatility": "v",
            "function_owner": f"halpha_{environment}_migration",
        }
        for name, contract in CRITICAL_TRIGGER_FUNCTIONS.items()
    }
    critical_contract = {
        "live_activation_safety_index": [
            False,
            True,
            True,
            ["environment_id", "account_ref"],
            LIVE_ACTIVATION_SAFETY_INDEX_PREDICATE,
        ],
        "constraints": constraints,
        "triggers": triggers,
        "trigger_inventory": sorted(
            [contract["table"], name]
            for name, contract in CRITICAL_TRIGGER_FUNCTIONS.items()
        ),
        "review_version_chain_fk": {
            "table": "review",
            "type": "f",
            "validated": True,
            "definition": (
                "FOREIGN KEY (environment_id, review_id, previous_version) "
                "REFERENCES halpha.review(environment_id, review_id, review_version)"
            ),
        },
        "qualified": True,
    }
    exact = {"exact": True}
    return {
        "revision": verify_database_boundary.HEAD,
        "product_tables": sorted(PRODUCT_RECORD_FAMILIES),
        "critical_contract": critical_contract,
        "acl_boundary": {
            "database": {
                "owner": f"halpha_{environment}_migration",
                "collation": "C",
                "ctype": "C",
                "acl": exact,
            },
            "schema_owners": exact,
            "schema_acl": exact,
            "table_owners": exact,
            "table_acl": exact,
            "column_acl": exact,
            "function_owners": exact,
            "function_acl": exact,
        },
        "app": {
            "command_insert": True,
            "execution_action_insert": False,
            "venue_fact_insert": False,
            "write_matrix": verify_database_boundary.EXPECTED_APP_WRITES,
        },
        "executor": {
            "command_insert": False,
            "execution_action_insert": True,
            "venue_fact_insert": True,
            "trade_plan_version_insert": False,
            "write_matrix": verify_database_boundary.EXPECTED_EXECUTOR_WRITES,
        },
        "backup": {
            "all_product_tables_select": True,
            "any_product_table_insert": False,
            "write_matrix": {},
        },
        "app_reader": (
            {
                "all_product_tables_select": True,
                "database_temporary": False,
                "write_matrix": {},
            }
            if environment.startswith("live_")
            else None
        ),
    }


def test_database_qualification_rejects_any_missing_or_allowed_crossing() -> None:
    matrix = {
        f"{source}_{role}_to_{target}": True
        for source in verify_database_boundary.ENVIRONMENTS
        for target in verify_database_boundary.ENVIRONMENTS
        if source != target
        for role in ROLE_KINDS_BY_ENVIRONMENT[source]
    }
    evidence = {
        "environments": {
            "demo": _qualified_environment("demo"),
            "live_copy": _qualified_environment("live_copy"),
            "live_personal": _qualified_environment("live_personal"),
        },
        "managed_role_boundary": {
            "attributes": {
                role: deepcopy(
                    verify_database_boundary.EXPECTED_ROLE_ATTRIBUTES
                )
                for role in verify_database_boundary._managed_role_names()
            },
            "memberships": [],
        },
        "cross_database_connect_rejected": matrix,
    }

    assert verify_database_boundary._qualified(evidence) is True

    matrix["live_copy_backup_to_demo"] = False
    assert verify_database_boundary._qualified(evidence) is False

    matrix.pop("live_copy_backup_to_demo")
    assert verify_database_boundary._qualified(evidence) is False


def test_database_qualification_rejects_role_attribute_or_membership_drift() -> None:
    boundary = {
        "attributes": {
            role: deepcopy(verify_database_boundary.EXPECTED_ROLE_ATTRIBUTES)
            for role in verify_database_boundary._managed_role_names()
        },
        "memberships": [],
    }

    assert (
        verify_database_boundary._managed_role_boundary_qualified(boundary)
        is True
    )

    drifted_attributes = deepcopy(boundary)
    drifted_attributes["attributes"]["halpha_live_copy_executor"]["inherit"] = True
    assert (
        verify_database_boundary._managed_role_boundary_qualified(
            drifted_attributes
        )
        is False
    )

    inherited_membership = deepcopy(boundary)
    inherited_membership["memberships"] = [
        {
            "granted_role": "external_admin",
            "member_role": "halpha_live_copy_executor",
        }
    ]
    assert (
        verify_database_boundary._managed_role_boundary_qualified(
            inherited_membership
        )
        is False
    )


def test_database_qualification_rejects_index_or_trigger_semantic_drift() -> None:
    environment = _qualified_environment("live_copy")
    contract = environment["critical_contract"]

    assert (
        verify_database_boundary._critical_contract_qualified(
            contract,
            "live_copy",
        )
        is True
    )

    wrong_columns = deepcopy(contract)
    wrong_columns["live_activation_safety_index"][3] = [
        "environment_id",
        "instrument_ref",
    ]
    assert (
        verify_database_boundary._critical_contract_qualified(
            wrong_columns,
            "live_copy",
        )
        is False
    )

    wrong_predicate = deepcopy(contract)
    wrong_predicate["live_activation_safety_index"][4] = (
        "lifecycle::text <> 'COMPLETED'::text"
    )
    assert (
        verify_database_boundary._critical_contract_qualified(
            wrong_predicate,
            "live_copy",
        )
        is False
    )

    disabled_trigger = deepcopy(contract)
    disabled_trigger["triggers"][
        "trg_plan_activation_identity_immutable"
    ]["enabled"] = "D"
    assert (
        verify_database_boundary._critical_contract_qualified(
            disabled_trigger,
            "live_copy",
        )
        is False
    )

    empty_function = deepcopy(contract)
    empty_function["triggers"][
        "trg_plan_activation_identity_immutable"
    ]["body_sha256"] = "0" * 64
    assert (
        verify_database_boundary._critical_contract_qualified(
            empty_function,
            "live_copy",
        )
        is False
    )

    unknown_trigger = deepcopy(contract)
    unknown_trigger["trigger_inventory"].append(
        ["plan_activation", "zzz_mutate_identity"]
    )
    unknown_trigger["trigger_inventory"].sort()
    assert (
        verify_database_boundary._critical_contract_qualified(
            unknown_trigger,
            "live_copy",
        )
        is False
    )


def test_database_qualification_rejects_any_acl_or_owner_drift() -> None:
    environment = _qualified_environment("live_copy")

    assert (
        verify_database_boundary._environment_qualified(
            "live_copy",
            environment,
        )
        is True
    )

    for key in (
        "schema_acl",
        "table_acl",
        "column_acl",
        "function_acl",
    ):
        drift = deepcopy(environment)
        drift["acl_boundary"][key] = {"exact": False}
        assert (
            verify_database_boundary._environment_qualified(
                "live_copy",
                drift,
            )
            is False
        )

    wrong_owner = deepcopy(environment)
    wrong_owner["acl_boundary"]["database"]["owner"] = "postgres"
    assert (
        verify_database_boundary._environment_qualified(
            "live_copy",
            wrong_owner,
        )
        is False
    )
