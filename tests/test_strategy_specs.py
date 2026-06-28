from __future__ import annotations

import json
from types import ModuleType

from halpha.quant.registry import (
    SUPPORTED_STRATEGY_NAMES,
    get_strategy_definition,
    get_supported_strategy_spec,
    supported_strategy_spec_records,
    supported_strategy_specs,
)
from halpha.quant.strategies import (
    bollinger_rsi_reversion,
    breakout_atr_trend,
    sma_cross_trend,
    tsmom_vol_scaled,
)


EXPECTED_ORDER = [
    "tsmom_vol_scaled",
    "breakout_atr_trend",
    "sma_cross_trend",
    "bollinger_rsi_reversion",
]
STRATEGY_MODULES = {
    "tsmom_vol_scaled": tsmom_vol_scaled,
    "breakout_atr_trend": breakout_atr_trend,
    "sma_cross_trend": sma_cross_trend,
    "bollinger_rsi_reversion": bollinger_rsi_reversion,
}


def test_supported_strategy_specs_are_deterministic() -> None:
    specs = supported_strategy_specs()

    assert [spec.name for spec in specs] == EXPECTED_ORDER
    assert set(EXPECTED_ORDER) == set(SUPPORTED_STRATEGY_NAMES)


def test_strategy_definition_includes_spec_without_losing_callables() -> None:
    definition = get_strategy_definition("tsmom_vol_scaled")

    assert definition is not None
    assert definition.name == "tsmom_vol_scaled"
    assert definition.spec.name == "tsmom_vol_scaled"
    assert definition.spec.family == "trend"
    assert callable(definition.run)
    assert callable(definition.failed_params)
    assert callable(definition.signal_records)


def test_registry_returns_complete_spec_records() -> None:
    records = supported_strategy_spec_records()

    assert [record["name"] for record in records] == EXPECTED_ORDER
    for record in records:
        assert record["schema_version"] == 1
        assert record["family"]
        assert record["version"]
        assert record["description"]
        assert record["supported_market_types"] == ["spot", "swap"]
        assert record["required_inputs"] == [
            {
                "input_type": "ohlcv",
                "required": True,
                "time_alignment": "closed_bar_no_lookahead",
                "fields": ["open_time", "open", "high", "low", "close", "volume"],
            }
        ]
        assert record["output_position_policy"] == "research_long_flat_target_exposure"
        assert record["default_params"]
        assert set(record["default_params"]) == set(record["parameter_schema"])
        assert set(record["default_params"]) == set(record["optimization_space"])
        assert record["minimum_rows_policy"]["minimum_rows_with_default_params"] > 0
        assert record["risk_notes"]


def test_strategy_spec_records_are_json_serializable() -> None:
    records = supported_strategy_spec_records()

    serialized = json.dumps(records, sort_keys=True)

    assert "tsmom_vol_scaled" in serialized
    assert "optimization_space" in serialized


def test_supported_strategy_spec_lookup_rejects_unknown_names() -> None:
    assert get_supported_strategy_spec("missing") is None
    assert get_strategy_definition("missing") is None


def test_strategy_specs_include_dashboard_parameter_metadata() -> None:
    spec = get_supported_strategy_spec("bollinger_rsi_reversion")

    assert spec is not None
    record = spec.to_record()
    assert record["parameter_schema"]["rsi_oversold"]["type"] == "number"
    assert record["parameter_schema"]["rsi_oversold"]["minimum"] == 0.0
    assert record["parameter_schema"]["rsi_oversold"]["maximum"] == 100.0
    assert record["parameter_schema"]["rsi_oversold"]["optimization_enabled"] is True
    assert record["optimization_space"]["rsi_oversold"]["values"] == [25.0, 30.0]


def test_current_strategy_modules_use_spec_defaults() -> None:
    for name, module in STRATEGY_MODULES.items():
        definition = get_strategy_definition(name)
        assert definition is not None
        assert module.NAME == name
        assert module.SPEC is definition.spec
        assert module.DEFAULT_PARAMS == definition.spec.default_params
        assert definition.spec.output_position_policy == "research_long_flat_target_exposure"


def test_current_strategy_minimum_rows_match_specs() -> None:
    for name, module in STRATEGY_MODULES.items():
        spec = get_supported_strategy_spec(name)
        assert spec is not None
        assert _minimum_rows(module) == spec.minimum_rows_policy["minimum_rows_with_default_params"]


def _minimum_rows(module: ModuleType) -> int:
    return module._minimum_rows(module.DEFAULT_PARAMS)
