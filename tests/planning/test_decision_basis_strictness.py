import pytest
from pydantic import ValidationError

from halpha.domain_values import content_digest
from halpha.planning.registry import build_fixed_plan_basis
from halpha.planning.repository import _fixed_decision_basis


def test_legacy_fixed_strategy_basis_is_rejected() -> None:
    parameters = {"direction": "LONG", "entry_valid_minutes": 60}

    with pytest.raises(ValidationError):
        _fixed_decision_basis(
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


def test_fixed_strategy_basis_rejects_removed_legacy_marker() -> None:
    basis = build_fixed_plan_basis(
        "ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
        {"direction": "LONG"},
        product_build_id="a" * 64,
    ).model_dump(mode="json")
    basis["legacy_unverified"] = True

    with pytest.raises(ValidationError):
        _fixed_decision_basis(basis)
