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
    bollinger_rsi_long_short,
    bollinger_rsi_reversion,
    breakout_atr_trend,
    cross_sectional_momentum,
    pair_zscore_reversion,
    sma_cross_long_short,
    sma_cross_trend,
    signed_tsmom_trend,
    tsmom_vol_scaled,
)


EXPECTED_ORDER = [
    "tsmom_vol_scaled",
    "signed_tsmom_trend",
    "breakout_atr_trend",
    "sma_cross_trend",
    "sma_cross_long_short",
    "pair_zscore_reversion",
    "cross_sectional_momentum",
    "bollinger_rsi_reversion",
    "bollinger_rsi_long_short",
]
STRATEGY_MODULES = {
    "tsmom_vol_scaled": tsmom_vol_scaled,
    "signed_tsmom_trend": signed_tsmom_trend,
    "breakout_atr_trend": breakout_atr_trend,
    "sma_cross_trend": sma_cross_trend,
    "sma_cross_long_short": sma_cross_long_short,
    "pair_zscore_reversion": pair_zscore_reversion,
    "cross_sectional_momentum": cross_sectional_momentum,
    "bollinger_rsi_reversion": bollinger_rsi_reversion,
    "bollinger_rsi_long_short": bollinger_rsi_long_short,
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
        if record["name"] == "cross_sectional_momentum":
            assert record["supported_market_types"] == ["swap"]
        else:
            assert record["supported_market_types"] == ["spot", "swap"]
        if record["name"] == "pair_zscore_reversion":
            assert [item["leg_id"] for item in record["required_inputs"]] == ["spread_leg_a", "spread_leg_b"]
            assert record["required_inputs"][0]["time_alignment"] == "closed_bar_no_lookahead"
        elif record["name"] == "cross_sectional_momentum":
            assert record["required_inputs"][0]["instrument_role"] == "ranked_universe_member"
            assert record["required_inputs"][0]["minimum_instrument_count"] == 3
        else:
            assert record["required_inputs"] == [
                {
                    "input_type": "ohlcv",
                    "required": True,
                    "time_alignment": "closed_bar_no_lookahead",
                    "fields": ["open_time", "open", "high", "low", "close", "volume"],
                }
            ]
        if record["name"] in {"signed_tsmom_trend", "sma_cross_long_short", "bollinger_rsi_long_short"}:
            assert record["output_position_policy"] == "research_signed_target_exposure"
        elif record["name"] in {"pair_zscore_reversion", "cross_sectional_momentum"}:
            assert record["output_position_policy"] == "research_multi_leg_target_exposure"
        else:
            assert record["output_position_policy"] == "research_long_flat_target_exposure"
        assert record["default_params"]
        assert set(record["default_params"]) == set(record["parameter_schema"])
        assert set(record["default_params"]) == set(record["optimization_space"])
        assert record["minimum_rows_policy"]["minimum_rows_with_default_params"] > 0
        assert record["risk_notes"]
        assert isinstance(record["supported_filters"], list)
        assert isinstance(record["supported_features"], list)
        if record["name"] == "signed_tsmom_trend":
            assert record["supported_filters"][0]["filter_id"] == "realized_volatility_max_pct_v1"
            assert record["supported_filters"][0]["required"] is False
            assert record["supported_features"][0]["feature_id"] == "derivatives_feature:funding_rate:funding_rate_v1"
            assert record["supported_features"][0]["time_alignment"] == "as_of_and_first_seen_no_lookahead"
        else:
            assert record["supported_filters"] == []
            assert record["supported_features"] == []


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
        if name in {"signed_tsmom_trend", "sma_cross_long_short", "bollinger_rsi_long_short"}:
            assert definition.spec.output_position_policy == "research_signed_target_exposure"
        elif name == "pair_zscore_reversion":
            assert definition.spec.output_position_policy == "research_multi_leg_target_exposure"
            assert definition.multi_leg_signal_records is module.pair_signal_records
            assert definition.multi_leg_backtest is module.evaluate_pair_backtest
        elif name == "cross_sectional_momentum":
            assert definition.spec.output_position_policy == "research_multi_leg_target_exposure"
            assert definition.multi_leg_signal_records is module.universe_signal_records
            assert definition.multi_leg_backtest is module.evaluate_universe_backtest
        else:
            assert definition.spec.output_position_policy == "research_long_flat_target_exposure"


def test_current_strategy_minimum_rows_match_specs() -> None:
    for name, module in STRATEGY_MODULES.items():
        spec = get_supported_strategy_spec(name)
        assert spec is not None
        assert _minimum_rows(module) == spec.minimum_rows_policy["minimum_rows_with_default_params"]


def _minimum_rows(module: ModuleType) -> int:
    return module._minimum_rows(module.DEFAULT_PARAMS)
