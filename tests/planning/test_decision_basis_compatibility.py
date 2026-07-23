from halpha.domain_values import content_digest
from halpha.planning.registry import DecisionBasisKind
from halpha.planning.repository import _fixed_decision_basis


def test_migration_backfilled_legacy_strategy_basis_remains_readable_but_unverified() -> None:
    parameters = {"direction": "LONG", "entry_valid_minutes": 60}
    basis = _fixed_decision_basis(
        {
            "kind": "STRATEGY_SIGNAL",
            "decision_basis_ref": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT@1.0.1",
            "strategy_definition_ref": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT@1.0.1",
            "parameter_schema_version": "1.3.0",
            "parameters": parameters,
            "parameter_digest": content_digest(parameters),
            "product_build_id": "a" * 64,
        }
    )

    assert basis.kind is DecisionBasisKind.STRATEGY_SIGNAL
    assert basis.strategy_id == "ONE_SHOT_DONCHIAN_ATR_BREAKOUT"
    assert basis.strategy_version == "1.0.1"
    assert basis.normalized_parameters == parameters
    assert basis.legacy_unverified is True
    assert basis.implementation_digest is None
