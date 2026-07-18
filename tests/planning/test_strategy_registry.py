from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from halpha.domain_values import content_digest
from halpha.planning.indicators import IndicatorBar, native_donchian_atr_snapshot
from halpha.planning.registry import (
    ONE_SHOT_STRATEGY_ID,
    OneShotParameters,
    build_fixed_plan_basis,
    describe_strategy,
    strategy_parameter_schema,
    render_strategy_registry,
    validate_parameters,
)
from halpha.planning.transitions import bar_source_identity
from halpha.planning.strategies.one_shot import (
    ActivationStrategyState,
    EntryEvaluationInput,
    InstrumentQuantityRules,
    OneShotDonchianAtrLogic,
)


ROOT = Path(__file__).resolve().parents[2]


def _parameters(**updates: object) -> dict[str, object]:
    values: dict[str, object] = {"direction": "LONG"}
    values.update(updates)
    return values


def _bars(count: int = 20) -> tuple[IndicatorBar, ...]:
    start = 1_767_225_600_000_000_000
    bars = []
    for index in range(count):
        close = 100 + index
        bars.append(
            IndicatorBar(
                open=str(close - 1),
                high=str(close + 2),
                low=str(close - 2),
                close=str(close),
                volume="1",
                ts_event_ns=start + (index + 1) * 900_000_000_000,
            )
        )
    return tuple(bars)


def test_static_registry_and_schema_are_build_bound() -> None:
    definition = describe_strategy(ONE_SHOT_STRATEGY_ID)
    schema = strategy_parameter_schema(ONE_SHOT_STRATEGY_ID)
    assert definition.strategy_version == "1.0.0"
    assert definition.implementation_digest == sha256(
        (ROOT / "src/halpha/planning/strategies/one_shot.py").read_bytes()
    ).hexdigest()
    assert schema["additionalProperties"] is False
    assert schema["properties"]["initial_stop_atr_multiple"]["type"] == "string"
    assert definition.native_indicators == (
        "nautilus_trader.indicators.DonchianChannel",
        "nautilus_trader.indicators.AverageTrueRange",
    )
    assert (ROOT / "src/halpha/planning/strategy_registry.json").read_text(
        encoding="utf-8"
    ) == render_strategy_registry()


def test_parameter_validation_is_authoritative_and_exact() -> None:
    normalized = validate_parameters(ONE_SHOT_STRATEGY_ID, _parameters())
    assert normalized["initial_stop_atr_multiple"] == "1.5"
    assert normalized["take_profit_1_fraction"] == "0.5"
    with pytest.raises(ValidationError):
        validate_parameters(ONE_SHOT_STRATEGY_ID, _parameters(extra="not allowed"))
    with pytest.raises(ValidationError):
        validate_parameters(
            ONE_SHOT_STRATEGY_ID,
            _parameters(take_profit_1_r="3.0", take_profit_2_r="3.0"),
        )
    with pytest.raises(ValidationError):
        validate_parameters(
            ONE_SHOT_STRATEGY_ID,
            _parameters(initial_stop_atr_multiple=float("nan")),
        )


def test_fixed_basis_binds_parameters_build_and_evidence() -> None:
    basis = build_fixed_plan_basis(
        ONE_SHOT_STRATEGY_ID,
        _parameters(direction="SHORT"),
        build_digest="a" * 64,
        evidence_digest="b" * 64,
        evidence_scope={"environment": "DEMO", "instrument": "BTCUSDT-PERP"},
    )
    assert basis.normalized_parameters["direction"] == "SHORT"
    assert basis.build_digest == "a" * 64
    assert basis.parameter_digest == content_digest(basis.normalized_parameters)


def test_native_indicator_boundary_uses_qualified_classes() -> None:
    snapshot = native_donchian_atr_snapshot(
        instrument_id="BTCUSDT-PERP.BINANCE",
        lookback=20,
        bars=_bars(),
    )
    assert snapshot.initialized is True
    assert snapshot.upper == "121"
    assert snapshot.lower == "98"
    assert float(snapshot.atr) > 0
    with pytest.raises(ValueError, match="INDICATOR_WINDOW_ORDER_INVALID"):
        native_donchian_atr_snapshot(
            instrument_id="BTCUSDT-PERP.BINANCE",
            lookback=20,
            bars=tuple(reversed(_bars())),
        )


def test_one_shot_logic_is_deterministic_and_consumes_only_explicit_state() -> None:
    now = datetime(2026, 7, 17, 8, tzinfo=UTC)
    snapshot = native_donchian_atr_snapshot(
        instrument_id="BTCUSDT-PERP.BINANCE",
        lookback=20,
        bars=_bars(),
    )
    evaluation = EntryEvaluationInput(
        activation_id="activation-1",
        instrument_id="BTCUSDT-PERP.BINANCE",
        source_identity=bar_source_identity(
            activation_id="activation-1",
            rule_id="ENTRY_BREAKOUT",
            bar_type="BTCUSDT-PERP.BINANCE-15-MINUTE-LAST-INTERNAL",
            ts_event_ns=snapshot.source_cutoff_ns,
        ),
        source_cutoff=now - timedelta(minutes=1),
        input_digest="c" * 64,
        decision_at=now,
        valid_until=now + timedelta(seconds=30),
        confirmation_closes=("121.5", "121.6"),
        indicators=snapshot,
        reference_price="121.7",
        reference_source="BACKTEST_LAST_BAR_PROXY",
        max_allowed_loss="100",
        max_notional="1000",
        max_margin="200",
        effective_leverage="5",
        taker_fee_rate="0.0006",
        rules=InstrumentQuantityRules(
            step_size="0.001",
            price_tick_size="0.1",
            min_quantity="0.001",
            max_market_quantity="100",
            min_notional="5",
        ),
    )
    logic = OneShotDonchianAtrLogic(OneShotParameters(direction="LONG"))
    first = logic.evaluate_entry(evaluation, ActivationStrategyState())
    replay = logic.evaluate_entry(evaluation, ActivationStrategyState())
    consumed = logic.evaluate_entry(
        evaluation,
        ActivationStrategyState(entry_opportunity_consumed=True),
    )
    paused = logic.evaluate_entry(
        evaluation,
        ActivationStrategyState(run_state="PAUSED"),
    )
    assert first == replay
    assert first.proposal is not None
    assert first.proposal.proposal_digest == replay.proposal.proposal_digest
    assert consumed.proposal is None
    assert consumed.reason_code == "ENTRY_OPPORTUNITY_CONSUMED"
    assert paused.proposal is None
    assert paused.reason_code == "NEW_RISK_NOT_ALLOWED"


def test_pure_strategy_source_has_no_framework_or_venue_write_dependency() -> None:
    path = ROOT / "src/halpha/planning/strategies/one_shot.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert not any(name.startswith("nautilus_trader") for name in imports)
    forbidden = (
        "submit_order",
        "cancel_order",
        "modify_order",
        "close_position",
        "market_exit",
        "ExecutionClient",
        "OrderFactory",
        "TradingNode",
    )
    assert all(token not in source for token in forbidden)
