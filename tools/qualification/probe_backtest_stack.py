from __future__ import annotations

import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from nautilus_trader.analysis import MaxDrawdown
from nautilus_trader.analysis import ProfitFactor
from nautilus_trader.analysis import ReportProvider
from nautilus_trader.analysis import WinRate
from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.models import LatencyModel
from nautilus_trader.backtest.models import MakerTakerFeeModel
from nautilus_trader.backtest.models import OneTickSlippageFillModel
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.data.config import DataEngineConfig
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.enums import OmsType
from nautilus_trader.model.instruments import CryptoPerpetual
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.persistence.wranglers import BarDataWrangler
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.trading.config import StrategyConfig

from tools.qualification.nautilus_fixtures import BacktestQualificationStrategy


BUILD_DIRECTORY = REPOSITORY_ROOT / "build" / "qualification"
BAR_TYPE = BarType.from_str("BTCUSDT-PERP.BINANCE-1-MINUTE-LAST-EXTERNAL")
CONSERVATIVE_FEE_RATE = Decimal("0.0006")
LATENCY_NANOS = {
    "base": 1_000_000,
    "insert": 2_000_000,
    "update": 3_000_000,
    "cancel": 4_000_000,
}


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _build_instrument() -> CryptoPerpetual:
    template = TestInstrumentProvider.btcusdt_perp_binance()
    return CryptoPerpetual(
        instrument_id=template.id,
        raw_symbol=template.raw_symbol,
        base_currency=template.base_currency,
        quote_currency=template.quote_currency,
        settlement_currency=template.settlement_currency,
        is_inverse=template.is_inverse,
        price_precision=template.price_precision,
        size_precision=template.size_precision,
        price_increment=template.price_increment,
        size_increment=template.size_increment,
        ts_event=template.ts_event,
        ts_init=template.ts_init,
        multiplier=template.multiplier,
        lot_size=template.lot_size,
        max_quantity=template.max_quantity,
        min_quantity=template.min_quantity,
        min_notional=template.min_notional,
        max_price=template.max_price,
        min_price=template.min_price,
        margin_init=template.margin_init,
        margin_maint=template.margin_maint,
        maker_fee=CONSERVATIVE_FEE_RATE,
        taker_fee=CONSERVATIVE_FEE_RATE,
    )


def _build_bars(instrument: CryptoPerpetual) -> list[Bar]:
    index = pd.date_range("2026-01-01T00:01:00Z", periods=20, freq="min")
    frame = pd.DataFrame(
        {
            "open": [100_000.0 + offset for offset in range(20)],
            "high": [100_002.0 + offset for offset in range(20)],
            "low": [99_998.0 + offset for offset in range(20)],
            "close": [100_001.0 + offset for offset in range(20)],
            "volume": [1_000.0] * 20,
        },
        index=index,
    )
    return BarDataWrangler(BAR_TYPE, instrument).process(frame)


def _configuration() -> dict[str, object]:
    return {
        "pandas": pd.__version__,
        "bar_type": str(BAR_TYPE),
        "bar_count": 20,
        "data_engine": {
            "time_bars_interval_type": "left-open",
            "time_bars_timestamp_on_close": True,
            "time_bars_skip_first_non_full_bar": True,
            "time_bars_build_with_no_updates": False,
            "validate_data_sequence": True,
        },
        "venue": {
            "oms_type": "NETTING",
            "account_type": "MARGIN",
            "starting_balance": "100000 USDT",
            "default_leverage": "5",
            "use_reduce_only": True,
            "bar_execution": True,
            "bar_adaptive_high_low_ordering": True,
            "liquidity_consumption": False,
        },
        "models": {
            "fee": "MakerTakerFeeModel",
            "instrument_maker_fee": str(CONSERVATIVE_FEE_RATE),
            "instrument_taker_fee": str(CONSERVATIVE_FEE_RATE),
            "slippage": "OneTickSlippageFillModel",
            "latency": LATENCY_NANOS,
            "funding": "NOT_MODELED",
        },
        "catalog": "ParquetDataCatalog",
        "wrangler": "BarDataWrangler",
        "reporter": "ReportProvider",
        "strategy": "BacktestQualificationStrategy",
    }


def main() -> int:
    errors: list[str] = []
    configuration = _configuration()
    evidence: dict[str, object] = {
        "configuration": configuration,
        "config_digest_sha256": _digest(configuration),
        "funding_model": "NOT_MODELED",
        "funding_data_injected": False,
        "product_runtime_or_records_created": False,
    }
    engine: BacktestEngine | None = None
    BUILD_DIRECTORY.mkdir(parents=True, exist_ok=True)
    try:
        instrument = _build_instrument()
        bars = _build_bars(instrument)
        evidence["wrangler"] = {
            "input_rows": 20,
            "output_bars": len(bars),
            "first_ts_event": bars[0].ts_event,
            "last_ts_event": bars[-1].ts_event,
        }
        if len(bars) != 20:
            errors.append("WRANGLER_BAR_COUNT_MISMATCH")

        with TemporaryDirectory(dir=BUILD_DIRECTORY) as catalog_path:
            catalog = ParquetDataCatalog(catalog_path)
            catalog.write_data([instrument])
            catalog.write_data(bars)
            catalog_instruments = catalog.instruments(instrument_ids=[str(instrument.id)])
            catalog_bars = catalog.query(Bar, identifiers=[str(BAR_TYPE)])
            evidence["catalog"] = {
                "instrument_count": len(catalog_instruments),
                "bar_count": len(catalog_bars),
                "bar_timestamps_round_trip": [bar.ts_event for bar in catalog_bars]
                == [bar.ts_event for bar in bars],
                "temporary_catalog_persisted_after_probe": False,
            }
            if len(catalog_instruments) != 1:
                errors.append("CATALOG_INSTRUMENT_COUNT_MISMATCH")
            if len(catalog_bars) != len(bars):
                errors.append("CATALOG_BAR_COUNT_MISMATCH")
            if not evidence["catalog"]["bar_timestamps_round_trip"]:
                errors.append("CATALOG_BAR_TIMESTAMP_MISMATCH")

            engine = BacktestEngine(
                BacktestEngineConfig(
                    data_engine=DataEngineConfig(
                        time_bars_interval_type="left-open",
                        time_bars_timestamp_on_close=True,
                        time_bars_skip_first_non_full_bar=True,
                        time_bars_build_with_no_updates=False,
                        validate_data_sequence=True,
                    ),
                    logging=LoggingConfig(log_level="ERROR", bypass_logging=True),
                    run_analysis=True,
                ),
            )
            engine.add_venue(
                venue=instrument.id.venue,
                oms_type=OmsType.NETTING,
                account_type=AccountType.MARGIN,
                starting_balances=[Money.from_str("100000 USDT")],
                base_currency=None,
                default_leverage=Decimal("5"),
                fill_model=OneTickSlippageFillModel(),
                fee_model=MakerTakerFeeModel(),
                latency_model=LatencyModel(
                    base_latency_nanos=LATENCY_NANOS["base"],
                    insert_latency_nanos=LATENCY_NANOS["insert"],
                    update_latency_nanos=LATENCY_NANOS["update"],
                    cancel_latency_nanos=LATENCY_NANOS["cancel"],
                ),
                use_reduce_only=True,
                bar_execution=True,
                bar_adaptive_high_low_ordering=True,
                liquidity_consumption=False,
            )
            engine.add_instrument(instrument)
            engine.add_data(catalog_bars)
            engine.portfolio.analyzer.register_statistic(ProfitFactor())
            engine.portfolio.analyzer.register_statistic(MaxDrawdown())
            engine.portfolio.analyzer.register_statistic(WinRate())
            strategy = BacktestQualificationStrategy(
                instrument_id=instrument.id,
                bar_type=BAR_TYPE,
                config=StrategyConfig(
                    strategy_id="B00BACKTEST",
                    order_id_tag="001",
                    manage_contingent_orders=False,
                    manage_gtd_expiry=False,
                    manage_stop=False,
                    external_order_claims=None,
                ),
            )
            engine.add_strategy(strategy)
            engine.run()

            result = engine.get_result()
            orders = engine.cache.orders()
            positions = engine.cache.positions()
            reporter = ReportProvider()
            orders_report = reporter.generate_orders_report(orders)
            fills_report = reporter.generate_order_fills_report(orders)
            positions_report = reporter.generate_positions_report(positions)
            commission_exact = True
            for fill in strategy.fills:
                amount_text, currency = fill["commission"].split()
                expected = (
                    Decimal(fill["last_price"])
                    * Decimal(fill["last_quantity"])
                    * CONSERVATIVE_FEE_RATE
                )
                if currency != "USDT" or Decimal(amount_text) != expected:
                    commission_exact = False

            evidence["engine"] = {
                "proposal_count": len(strategy.proposals),
                "proposals": strategy.proposals,
                "entry_submitted": strategy.entry_submitted,
                "exit_submitted": strategy.exit_submitted,
                "fill_count": len(strategy.fills),
                "fills": strategy.fills,
                "commission_matches_decimal_price_quantity_rate": commission_exact,
                "closed_positions": strategy.closed_positions,
                "open_positions_after_run": len(engine.cache.positions_open()),
                "total_orders": result.total_orders,
                "total_positions": result.total_positions,
                "exit_order_reduce_only": bool(len(orders) == 2 and orders[1].is_reduce_only),
                "one_shot_no_reentry": len(strategy.proposals) == 1 and result.total_orders == 2,
            }
            evidence["reports"] = {
                "orders_rows": len(orders_report),
                "order_fills_rows": len(fills_report),
                "positions_rows": len(positions_report),
                "pnl_statistic_names": sorted(
                    next(iter(result.stats_pnls.values())).keys()
                    if result.stats_pnls
                    else [],
                ),
                "return_statistic_names": sorted(result.stats_returns.keys()),
            }

            if len(strategy.proposals) != 1:
                errors.append("ONE_SHOT_PROPOSAL_COUNT_MISMATCH")
            if result.total_orders != 2 or len(strategy.fills) != 2:
                errors.append("ENTRY_EXIT_FILL_COUNT_MISMATCH")
            if strategy.closed_positions != 1 or engine.cache.positions_open():
                errors.append("POSITION_NOT_CLOSED_ONCE")
            if len(orders) != 2 or not orders[1].is_reduce_only:
                errors.append("EXIT_NOT_EXPLICIT_REDUCE_ONLY")
            if not commission_exact:
                errors.append("MAKER_TAKER_FEE_MODEL_DECIMAL_MISMATCH")
            if len(orders_report) != 2 or len(fills_report) != 2 or len(positions_report) != 1:
                errors.append("REPORT_PROVIDER_ROW_COUNT_MISMATCH")
    except Exception as exc:
        errors.append(f"BACKTEST_STACK_PROBE_FAILED:{type(exc).__name__}")
    finally:
        if engine is not None:
            try:
                engine.dispose()
                evidence["engine_disposed"] = True
            except Exception as exc:
                errors.append(f"BACKTEST_ENGINE_DISPOSE_FAILED:{type(exc).__name__}")
                evidence["engine_disposed"] = False

    evidence["errors"] = sorted(set(errors))
    evidence["status"] = "QUALIFIED" if not errors else "REJECTED"
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
