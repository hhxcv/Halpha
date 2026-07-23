from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "migrations"
    / "versions"
    / "20260723_0012_decision_basis_contract_hardening.py"
)


def test_decision_basis_contract_hardening_is_a_linear_followup() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision = "20260723_0012"' in source
    assert 'down_revision = "20260723_0011"' in source
    assert "op.create_table(" not in source


def test_strict_json_checks_fail_closed_and_bind_the_exact_direct_reference() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "ck_trade_plan_version_decision_basis_strict" in source
    assert "fixed_decision_basis ? 'kind'" in source
    assert "fixed_decision_basis ? 'decision_basis_ref'" in source
    assert "COALESCE(" in source
    assert "FALSE)" in source
    assert "fixed_decision_basis->>'decision_basis_ref' = decision_basis_ref" in source
    assert "decision_basis_ref = 'DIRECT_EXECUTION@1'" in source
    assert "ck_trade_plan_version_direct_schedule_strict" in source
    assert "ck_plan_activation_direct_schedule_strict" in source


def test_activation_basis_is_bound_to_the_selected_plan_version() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "uq_trade_plan_version_basis_identity" in source
    assert "fk_plan_activation_version_basis" in source
    assert (
        '("environment_id", "plan_version_ref", "decision_basis_ref")'
        in source
    )
    assert (
        '("environment_id", "plan_version_id", "decision_basis_ref")'
        in source
    )


def test_decision_basis_contract_hardening_downgrades_in_reverse_dependency_order() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    foreign_key = source.rindex('"fk_plan_activation_version_basis"')
    unique = source.rindex('"uq_trade_plan_version_basis_identity"')
    activation_check = source.rindex('"ck_plan_activation_direct_schedule_strict"')
    version_schedule_check = source.rindex(
        '"ck_trade_plan_version_direct_schedule_strict"'
    )
    version_basis_check = source.rindex(
        '"ck_trade_plan_version_decision_basis_strict"'
    )

    assert (
        foreign_key
        < unique
        < activation_check
        < version_schedule_check
        < version_basis_check
    )
