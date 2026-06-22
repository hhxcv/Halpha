from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from halpha.config import load_config
from halpha.market.derivatives_history import sync_derivatives_market_history
from halpha.market.derivatives_market_context import build_derivatives_market_context
from halpha.market.derivatives_market_views import build_derivatives_market_views
from halpha.pipeline import RunContext, run_pipeline
from halpha.storage import write_json


def test_derivatives_context_builds_extreme_funding_and_oi_expansion(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, data_classes=["funding_rate", "open_interest"], lookback=3)
    config = load_config(config_path)

    result = _run_until_context(config, config_path, _write_extreme_raw_stage)

    assert result.succeeded is True
    context = _context(result)
    manifest = _manifest(result)
    funding = _context_record(context, context_type="funding_pressure", period="8h")
    oi = _context_record(context, context_type="open_interest_pressure", period="1h")
    oi_snapshot = _context_record(context, context_type="open_interest_pressure", period="snapshot")

    assert context["status"] == "ok"
    assert context["counts"]["records"] == 3
    assert funding["status"] == "succeeded"
    assert funding["state"] == "extreme_positive_funding"
    assert funding["severity"] == "high"
    assert funding["metrics"]["latest_funding_rate"] == 0.0007
    assert funding["metrics"]["rolling_funding_rate_change"] == pytest.approx(0.0006)
    assert funding["thresholds"]["extreme_positive_funding_rate"] == 0.0005
    assert funding["evidence"][0]["source_artifact"] == "raw/derivatives_market_views.json"
    assert oi["status"] == "succeeded"
    assert oi["state"] == "sharp_open_interest_expansion"
    assert oi["severity"] == "high"
    assert oi["metrics"]["rolling_open_interest_change"] == 25
    assert oi["metrics"]["rolling_open_interest_change_pct"] == pytest.approx(0.25)
    assert oi_snapshot["state"] == "open_interest_level_only"
    assert manifest["artifacts"]["derivatives_market_context"] == "analysis/derivatives_market_context.json"
    assert manifest["counts"]["derivatives_market_context_records"] == 3
    assert manifest["derivatives_market_context"]["funding_pressure"] == 1
    assert manifest["derivatives_market_context"]["open_interest_pressure"] == 2


def test_derivatives_context_records_neutral_and_missing_states(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, data_classes=["funding_rate", "open_interest"], lookback=2)
    config = load_config(config_path)

    result = _run_until_context(config, config_path, _write_neutral_and_missing_raw_stage)

    assert result.succeeded is True
    context = _context(result)
    funding = _context_record(context, context_type="funding_pressure", period="8h")
    oi = _context_record(context, context_type="open_interest_pressure", period="1h")
    missing_snapshot = _context_record(context, context_type="open_interest_pressure", period="snapshot")

    assert context["status"] == "warning"
    assert funding["state"] == "neutral"
    assert funding["severity"] == "low"
    assert oi["state"] == "neutral"
    assert oi["metrics"]["rolling_open_interest_change_pct"] == pytest.approx(0.015)
    assert missing_snapshot["status"] == "unavailable"
    assert missing_snapshot["state"] == "unavailable"
    assert "view status is missing_history." in missing_snapshot["uncertainty"]
    assert context["counts"]["unavailable"] == 1


def test_derivatives_context_flags_stale_input(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, data_classes=["funding_rate"], lookback=2)
    config = load_config(config_path)

    result = _run_until_context(
        config,
        config_path,
        _write_stale_raw_stage,
        context_now="2026-06-18T01:02:00Z",
    )

    assert result.succeeded is True
    context = _context(result)
    funding = _context_record(context, context_type="funding_pressure", period="8h")

    assert context["status"] == "warning"
    assert funding["status"] == "stale"
    assert funding["state"] == "stale"
    assert funding["confidence"] == "low"
    assert any("latest observation is stale" in warning for warning in funding["warnings"])
    assert context["counts"]["stale"] == 1


def test_derivatives_context_flags_partial_source_failure(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, data_classes=["funding_rate"], lookback=2)
    config = load_config(config_path)

    result = _run_until_context(config, config_path, _write_partial_raw_stage)

    assert result.succeeded is True
    context = _context(result)
    funding = _context_record(context, context_type="funding_pressure", period="8h")

    assert context["status"] == "warning"
    assert funding["status"] == "partial"
    assert funding["state"] == "elevated_positive_funding"
    assert funding["confidence"] == "low"
    assert "source availability is partial." in funding["uncertainty"]
    assert "funding history source returned partial data" in funding["errors"]
    assert context["counts"]["partial"] == 1


def test_derivatives_context_builds_premium_and_basis_records(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, data_classes=["premium_index", "basis"], lookback=2)
    config = load_config(config_path)

    result = _run_until_context(config, config_path, _write_premium_basis_raw_stage)

    assert result.succeeded is True
    context = _context(result)
    manifest = _manifest(result)
    premium = _context_record(context, context_type="premium_basis_state", period="snapshot")
    basis = _context_record(context, context_type="premium_basis_state", period="1h")

    assert context["status"] == "ok"
    assert premium["status"] == "succeeded"
    assert premium["state"] == "neutral"
    assert premium["metrics"]["latest_premium_rate"] == 0.0005
    assert premium["metrics"]["units"]["premium_rate"] == "ratio"
    assert basis["status"] == "succeeded"
    assert basis["state"] == "basis_stressed"
    assert basis["severity"] == "high"
    assert basis["metrics"]["latest_basis_rate"] == 0.006
    assert basis["metrics"]["contract_type"] == "CURRENT_QUARTER"
    assert basis["metrics"]["units"]["basis_rate"] == "ratio"
    assert manifest["derivatives_market_context"]["premium_basis_state"] == 2
    assert manifest["counts"]["derivatives_market_context_premium_basis_state"] == 2


def test_derivatives_context_records_stretched_and_inverted_premium_basis(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, data_classes=["premium_index", "basis"], lookback=2)
    config = load_config(config_path)

    result = _run_until_context(config, config_path, _write_stretched_inverted_raw_stage)

    assert result.succeeded is True
    context = _context(result)
    premium = _context_record(context, context_type="premium_basis_state", period="snapshot")
    basis = _context_record(context, context_type="premium_basis_state", period="1h")

    assert premium["state"] == "premium_stretched"
    assert premium["severity"] == "medium"
    assert premium["thresholds"]["stretched_abs_premium_rate"] == 0.001
    assert basis["state"] == "basis_inverted"
    assert basis["severity"] == "medium"


def test_derivatives_context_flags_stale_and_missing_premium_basis(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, data_classes=["premium_index", "basis"], lookback=2)
    config = load_config(config_path)

    result = _run_until_context(
        config,
        config_path,
        _write_stale_premium_raw_stage,
        context_now="2026-06-18T01:02:00Z",
    )

    assert result.succeeded is True
    context = _context(result)
    premium = _context_record(context, context_type="premium_basis_state", period="snapshot")
    basis = _context_record(context, context_type="premium_basis_state", period="1h")

    assert context["status"] == "warning"
    assert premium["status"] == "stale"
    assert premium["state"] == "stale"
    assert basis["status"] == "unavailable"
    assert basis["state"] == "unavailable"
    assert context["counts"]["stale"] == 1
    assert context["counts"]["unavailable"] == 1


def test_derivatives_context_flags_malformed_premium_basis_metrics(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, data_classes=["premium_index", "basis"], lookback=2)
    config = load_config(config_path)

    result = _run_until_context(config, config_path, _write_malformed_premium_basis_raw_stage)

    assert result.succeeded is True
    context = _context(result)
    premium = _context_record(context, context_type="premium_basis_state", period="snapshot")
    basis = _context_record(context, context_type="premium_basis_state", period="1h")

    assert premium["status"] == "insufficient"
    assert premium["state"] == "insufficient_evidence"
    assert "premium_rate metric is missing." in premium["warnings"]
    assert basis["status"] == "insufficient"
    assert basis["state"] == "insufficient_evidence"
    assert "basis_rate metric is missing." in basis["warnings"]
    assert context["counts"]["insufficient"] == 2


def test_derivatives_context_builds_normal_spread_depth_state(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, data_classes=["spread_depth"], lookback=1)
    config = load_config(config_path)

    result = _run_until_context(config, config_path, _write_normal_spread_depth_raw_stage)

    assert result.succeeded is True
    context = _context(result)
    depth = _context_record(context, context_type="liquidity_depth_state", period="snapshot")

    assert context["status"] == "ok"
    assert depth["status"] == "succeeded"
    assert depth["state"] == "neutral"
    assert depth["metrics"]["spread_bps"] == 5.0
    assert depth["metrics"]["snapshot_depth_limit"] == 20.0
    assert depth["metrics"]["units"]["spread_bps"] == "basis_points"
    assert "single depth snapshot" in depth["uncertainty"][0]
    assert _manifest(result)["derivatives_market_context"]["liquidity_depth_state"] == 1


def test_derivatives_context_flags_wide_spread_and_depth_imbalance(tmp_path: Path) -> None:
    wide_config_path = _write_config(tmp_path / "wide", data_classes=["spread_depth"], lookback=1)
    wide_config = load_config(wide_config_path)
    wide_result = _run_until_context(wide_config, wide_config_path, _write_wide_spread_depth_raw_stage)
    wide = _context_record(_context(wide_result), context_type="liquidity_depth_state", period="snapshot")

    imbalance_config_path = _write_config(tmp_path / "imbalance", data_classes=["spread_depth"], lookback=1)
    imbalance_config = load_config(imbalance_config_path)
    imbalance_result = _run_until_context(
        imbalance_config,
        imbalance_config_path,
        _write_imbalanced_spread_depth_raw_stage,
    )
    imbalance = _context_record(_context(imbalance_result), context_type="liquidity_depth_state", period="snapshot")

    assert wide["state"] == "spread_wide"
    assert wide["severity"] == "medium"
    assert imbalance["state"] == "depth_imbalanced"
    assert imbalance["severity"] == "medium"


def test_derivatives_context_flags_stale_and_unavailable_spread_depth(tmp_path: Path) -> None:
    stale_config_path = _write_config(tmp_path / "stale", data_classes=["spread_depth"], lookback=1)
    stale_config = load_config(stale_config_path)
    stale_result = _run_until_context(
        stale_config,
        stale_config_path,
        _write_stale_spread_depth_raw_stage,
        context_now="2026-06-18T01:02:00Z",
    )
    stale = _context_record(_context(stale_result), context_type="liquidity_depth_state", period="snapshot")

    missing_config_path = _write_config(tmp_path / "missing", data_classes=["spread_depth"], lookback=1)
    missing_config = load_config(missing_config_path)
    missing_result = _run_until_context(missing_config, missing_config_path, _noop_stage)
    missing = _context_record(_context(missing_result), context_type="liquidity_depth_state", period="snapshot")

    assert stale["status"] == "stale"
    assert stale["state"] == "stale"
    assert missing["status"] == "unavailable"
    assert missing["state"] == "unavailable"


def test_derivatives_context_flags_malformed_spread_depth_metrics(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, data_classes=["spread_depth"], lookback=1)
    config = load_config(config_path)

    result = _run_until_context(config, config_path, _write_malformed_spread_depth_raw_stage)

    assert result.succeeded is True
    context = _context(result)
    depth = _context_record(context, context_type="liquidity_depth_state", period="snapshot")

    assert depth["status"] == "insufficient"
    assert depth["state"] == "insufficient_evidence"
    assert "spread_bps metric is missing." in depth["warnings"]
    assert context["counts"]["insufficient"] == 1


def test_derivatives_context_records_unavailable_liquidation_source(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, data_classes=["liquidation_summary"], lookback=1)
    config = load_config(config_path)

    result = _run_until_context(config, config_path, _write_unavailable_liquidation_raw_stage)

    assert result.succeeded is True
    context = _context(result)
    liquidation = _context_record(context, context_type="liquidation_availability", period="source_availability")

    assert context["status"] == "warning"
    assert liquidation["status"] == "unavailable"
    assert liquidation["state"] == "unavailable"
    assert liquidation["severity"] == "unknown"
    assert liquidation["metrics"] == {
        "available_periodic_public_summary": False,
        "availability_records": 1,
    }
    assert liquidation["evidence"][0]["endpoint"] == "liquidation_order_streams"
    assert liquidation["evidence"][0]["method"] == "websocket_market_stream"
    assert liquidation["evidence"][0]["signed_rest_access"] == "USER_DATA"
    assert "stream snapshots include only the largest liquidation order" in liquidation["evidence"][0]["limitations"][1]
    assert "missing liquidation evidence must not lower risk." in liquidation["uncertainty"]
    assert _manifest(result)["derivatives_market_context"]["liquidation_availability"] == 1


def test_derivatives_context_flags_stale_liquidation_source(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, data_classes=["liquidation_summary"], lookback=1)
    config = load_config(config_path)

    result = _run_until_context(config, config_path, _write_stale_liquidation_raw_stage)

    assert result.succeeded is True
    context = _context(result)
    liquidation = _context_record(context, context_type="liquidation_availability", period="source_availability")

    assert liquidation["status"] == "stale"
    assert liquidation["state"] == "stale"
    assert liquidation["confidence"] == "low"
    assert "source availability is stale." in liquidation["uncertainty"]
    assert context["counts"]["stale"] == 1


def _run_until_context(
    config: dict[str, Any],
    config_path: Path,
    raw_stage,
    *,
    context_now: str = "2026-06-18T01:02:00Z",
):
    return run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_derivatives_market_context",
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_derivatives_market_data": raw_stage,
            "sync_derivatives_market_history": lambda config, run: sync_derivatives_market_history(
                config,
                run,
                now="2026-06-18T01:00:00Z",
            ),
            "build_derivatives_market_views": lambda config, run: build_derivatives_market_views(
                config,
                run,
                now="2026-06-18T01:01:00Z",
            ),
            "build_derivatives_market_context": lambda config, run: build_derivatives_market_context(
                config,
                run,
                now=context_now,
            ),
        },
    )


def _write_extreme_raw_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_raw(
        run,
        [
            _funding_item("2026-06-17T08:00:00Z", funding_rate=0.0001),
            _funding_item("2026-06-17T16:00:00Z", funding_rate=0.0003),
            _funding_item("2026-06-18T00:00:00Z", funding_rate=0.0007),
            _open_interest_item("snapshot", "2026-06-18T00:00:00Z", contracts=125),
            _open_interest_item("1h", "2026-06-17T22:00:00Z", contracts=100, value=1000),
            _open_interest_item("1h", "2026-06-17T23:00:00Z", contracts=110, value=1100),
            _open_interest_item("1h", "2026-06-18T00:00:00Z", contracts=125, value=1250),
        ],
        availability=[
            _availability("funding_rate", "8h", record_count=3),
            _availability("open_interest", "snapshot", request_class="open_interest_current", record_count=1),
            _availability("open_interest", "1h", request_class="open_interest_history", record_count=3),
        ],
    )
    return [RAW_DERIVATIVES_ARTIFACT]


def _write_neutral_and_missing_raw_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_raw(
        run,
        [
            _funding_item("2026-06-17T16:00:00Z", funding_rate=0.00003),
            _funding_item("2026-06-18T00:00:00Z", funding_rate=0.00005),
            _open_interest_item("1h", "2026-06-17T23:00:00Z", contracts=100, value=1000),
            _open_interest_item("1h", "2026-06-18T00:00:00Z", contracts=101.5, value=1015),
        ],
        availability=[
            _availability("funding_rate", "8h", record_count=2),
            _availability("open_interest", "1h", request_class="open_interest_history", record_count=2),
        ],
    )
    return [RAW_DERIVATIVES_ARTIFACT]


def _write_stale_raw_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_raw(
        run,
        [
            _funding_item("2026-06-10T16:00:00Z", funding_rate=0.0001),
            _funding_item("2026-06-11T00:00:00Z", funding_rate=0.0001),
        ],
        availability=[_availability("funding_rate", "8h", record_count=2)],
    )
    return [RAW_DERIVATIVES_ARTIFACT]


def _write_partial_raw_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_raw(
        run,
        [
            _funding_item("2026-06-17T16:00:00Z", funding_rate=0.0001),
            _funding_item("2026-06-18T00:00:00Z", funding_rate=0.0003),
        ],
        availability=[
            _availability(
                "funding_rate",
                "8h",
                status="partial",
                record_count=2,
                error_count=1,
                reason="one page failed",
            )
        ],
        errors=[
            {
                "data_class": "funding_rate",
                "symbol": "BTCUSDT",
                "period": "8h",
                "message": "funding history source returned partial data",
            }
        ],
    )
    return [RAW_DERIVATIVES_ARTIFACT]


def _write_premium_basis_raw_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_raw(
        run,
        [
            _premium_item("2026-06-18T00:00:00Z", premium_rate=0.0005),
            _basis_item("2026-06-17T23:00:00Z", basis_rate=0.001, contract_type="CURRENT_QUARTER"),
            _basis_item("2026-06-18T00:00:00Z", basis_rate=0.006, contract_type="CURRENT_QUARTER"),
        ],
        availability=[
            _availability("premium_index", "snapshot", request_class="premium_index", record_count=1),
            _availability("basis", "1h", request_class="basis", record_count=2),
        ],
    )
    return [RAW_DERIVATIVES_ARTIFACT]


def _write_stretched_inverted_raw_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_raw(
        run,
        [
            _premium_item("2026-06-18T00:00:00Z", premium_rate=0.0015),
            _basis_item("2026-06-17T23:00:00Z", basis_rate=0.0002, contract_type="CURRENT_QUARTER"),
            _basis_item("2026-06-18T00:00:00Z", basis_rate=-0.002, contract_type="CURRENT_QUARTER"),
        ],
        availability=[
            _availability("premium_index", "snapshot", request_class="premium_index", record_count=1),
            _availability("basis", "1h", request_class="basis", record_count=2),
        ],
    )
    return [RAW_DERIVATIVES_ARTIFACT]


def _write_stale_premium_raw_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_raw(
        run,
        [_premium_item("2026-06-11T00:00:00Z", premium_rate=0.0002)],
        availability=[_availability("premium_index", "snapshot", request_class="premium_index", record_count=1)],
    )
    return [RAW_DERIVATIVES_ARTIFACT]


def _write_malformed_premium_basis_raw_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_raw(
        run,
        [
            _premium_item("2026-06-18T00:00:00Z", premium_rate=None),
            _basis_item(
                "2026-06-17T23:00:00Z",
                basis_rate=None,
                contract_type="CURRENT_QUARTER",
            ),
            _basis_item(
                "2026-06-18T00:00:00Z",
                basis_rate=None,
                contract_type="CURRENT_QUARTER",
            ),
        ],
        availability=[
            _availability("premium_index", "snapshot", request_class="premium_index", record_count=1),
            _availability("basis", "1h", request_class="basis", record_count=2),
        ],
    )
    return [RAW_DERIVATIVES_ARTIFACT]


def _write_normal_spread_depth_raw_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_raw(
        run,
        [_spread_depth_item("2026-06-18T00:00:00Z", spread_bps=5.0, depth_imbalance=0.1)],
        availability=[_availability("spread_depth", "snapshot", request_class="order_book_depth", record_count=1)],
    )
    return [RAW_DERIVATIVES_ARTIFACT]


def _write_wide_spread_depth_raw_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_raw(
        run,
        [_spread_depth_item("2026-06-18T00:00:00Z", spread_bps=15.0, depth_imbalance=0.1)],
        availability=[_availability("spread_depth", "snapshot", request_class="order_book_depth", record_count=1)],
    )
    return [RAW_DERIVATIVES_ARTIFACT]


def _write_imbalanced_spread_depth_raw_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_raw(
        run,
        [_spread_depth_item("2026-06-18T00:00:00Z", spread_bps=5.0, depth_imbalance=0.6)],
        availability=[_availability("spread_depth", "snapshot", request_class="order_book_depth", record_count=1)],
    )
    return [RAW_DERIVATIVES_ARTIFACT]


def _write_stale_spread_depth_raw_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_raw(
        run,
        [_spread_depth_item("2026-06-11T00:00:00Z", spread_bps=5.0, depth_imbalance=0.1)],
        availability=[_availability("spread_depth", "snapshot", request_class="order_book_depth", record_count=1)],
    )
    return [RAW_DERIVATIVES_ARTIFACT]


def _write_malformed_spread_depth_raw_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_raw(
        run,
        [
            _spread_depth_item(
                "2026-06-18T00:00:00Z",
                spread_bps=None,
                depth_imbalance=0.1,
            )
        ],
        availability=[_availability("spread_depth", "snapshot", request_class="order_book_depth", record_count=1)],
    )
    return [RAW_DERIVATIVES_ARTIFACT]


def _write_unavailable_liquidation_raw_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_raw(
        run,
        [],
        availability=[_liquidation_availability(status="unavailable")],
    )
    return [RAW_DERIVATIVES_ARTIFACT]


def _write_stale_liquidation_raw_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_raw(
        run,
        [],
        availability=[
            _liquidation_availability(
                status="stale",
                reason="no recent liquidation stream snapshot was captured by the periodic run",
            )
        ],
    )
    return [RAW_DERIVATIVES_ARTIFACT]


RAW_DERIVATIVES_ARTIFACT = "raw/derivatives_market.json"


def _write_raw(
    run: RunContext,
    items: list[dict[str, Any]],
    *,
    availability: list[dict[str, Any]],
    errors: list[dict[str, Any]] | None = None,
) -> None:
    write_json(
        run.raw_dir / "derivatives_market.json",
        {
            "schema_version": 1,
            "artifact_type": "derivatives_market_raw",
            "collector": "derivatives_market",
            "collection_method": "public_http",
            "source": {"name": "binance_usdm", "url": "https://fapi.binance.com"},
            "collected_at": "2026-06-18T01:00:00Z",
            "items": items,
            "availability": availability,
            "warnings": [],
            "errors": errors or [],
        },
    )
    run.manifest["artifacts"]["raw_derivatives_market"] = RAW_DERIVATIVES_ARTIFACT


def _funding_item(as_of: str, *, funding_rate: float) -> dict[str, Any]:
    return {
        "item_id": f"derivatives_market:funding_rate:binance_usdm:BTCUSDT:8h:{as_of}",
        "data_class": "funding_rate",
        "source": "binance_usdm",
        "market_type": "usd_m_futures",
        "symbol": "BTCUSDT",
        "period": "8h",
        "as_of": as_of,
        "endpoint": "funding_rate_history",
        "request_class": "funding_rate_history",
        "metrics": {"funding_rate": funding_rate},
        "units": {"funding_rate": "ratio"},
        "raw_fields": {"fundingRate": f"{funding_rate:.8f}", "fundingTime": as_of},
        "warnings": [],
        "errors": [],
    }


def _open_interest_item(
    period: str,
    as_of: str,
    *,
    contracts: float,
    value: float | None = None,
) -> dict[str, Any]:
    request_class = "open_interest_current" if period == "snapshot" else "open_interest_history"
    metrics = {"open_interest_contracts": contracts}
    units = {"open_interest_contracts": "contracts"}
    if value is not None:
        metrics["open_interest_value"] = value
        units["open_interest_value"] = "quote_asset"
    return {
        "item_id": f"derivatives_market:open_interest:binance_usdm:BTCUSDT:{period}:{as_of}",
        "data_class": "open_interest",
        "source": "binance_usdm",
        "market_type": "usd_m_futures",
        "symbol": "BTCUSDT",
        "period": period,
        "as_of": as_of,
        "endpoint": request_class,
        "request_class": request_class,
        "metrics": metrics,
        "units": units,
        "raw_fields": {},
        "warnings": [],
        "errors": [],
    }


def _premium_item(as_of: str, *, premium_rate: float | None) -> dict[str, Any]:
    mark_price = 100.0 + (premium_rate or 0.0) * 100.0
    metrics = {
        "mark_price": mark_price,
        "index_price": 100.0,
    }
    units = {
        "mark_price": "quote_asset",
        "index_price": "quote_asset",
    }
    if premium_rate is not None:
        metrics["premium_rate"] = premium_rate
        units["premium_rate"] = "ratio"
    return {
        "item_id": f"derivatives_market:premium_index:binance_usdm:BTCUSDT:snapshot:{as_of}",
        "data_class": "premium_index",
        "source": "binance_usdm",
        "market_type": "usd_m_futures",
        "symbol": "BTCUSDT",
        "period": "snapshot",
        "as_of": as_of,
        "endpoint": "premium_index",
        "request_class": "premium_index",
        "metrics": metrics,
        "units": units,
        "raw_fields": {"time": as_of},
        "warnings": [],
        "errors": [],
    }


def _basis_item(
    as_of: str,
    *,
    basis_rate: float | None,
    contract_type: str,
) -> dict[str, Any]:
    metrics = {
        "basis": 10.0,
        "futures_price": 110.0,
        "index_price": 100.0,
    }
    units = {
        "basis": "quote_asset",
        "futures_price": "quote_asset",
        "index_price": "quote_asset",
    }
    if basis_rate is not None:
        metrics["basis_rate"] = basis_rate
        metrics["annualized_basis_rate"] = basis_rate * 365
        units["basis_rate"] = "ratio"
        units["annualized_basis_rate"] = "ratio"
    return {
        "item_id": f"derivatives_market:basis:binance_usdm:BTCUSDT:1h:{as_of}",
        "data_class": "basis",
        "source": "binance_usdm",
        "market_type": "usd_m_futures",
        "symbol": "BTCUSDT",
        "period": "1h",
        "as_of": as_of,
        "endpoint": "basis",
        "request_class": "basis",
        "metrics": metrics,
        "units": units,
        "raw_fields": {"contractType": contract_type},
        "warnings": [],
        "errors": [],
    }


def _spread_depth_item(
    as_of: str,
    *,
    spread_bps: float | None,
    depth_imbalance: float,
) -> dict[str, Any]:
    metrics = {
        "top_bid_price": 100.0,
        "top_bid_quantity": 10.0,
        "top_ask_price": 100.05,
        "top_ask_quantity": 8.0,
        "mid_price": 100.025,
        "spread": 0.05,
        "bid_depth_quantity": 120.0,
        "ask_depth_quantity": 100.0,
        "bid_depth_notional": 12000.0,
        "ask_depth_notional": 10000.0,
        "depth_imbalance": depth_imbalance,
        "snapshot_depth_limit": 20,
    }
    units = {
        "top_bid_price": "quote_asset",
        "top_bid_quantity": "base_asset",
        "top_ask_price": "quote_asset",
        "top_ask_quantity": "base_asset",
        "mid_price": "quote_asset",
        "spread": "quote_asset",
        "bid_depth_quantity": "base_asset",
        "ask_depth_quantity": "base_asset",
        "bid_depth_notional": "quote_asset",
        "ask_depth_notional": "quote_asset",
        "depth_imbalance": "ratio",
        "snapshot_depth_limit": "levels",
    }
    if spread_bps is not None:
        metrics["spread_bps"] = spread_bps
        units["spread_bps"] = "basis_points"
    return {
        "item_id": f"derivatives_market:spread_depth:binance_usdm:BTCUSDT:snapshot:{as_of}",
        "data_class": "spread_depth",
        "source": "binance_usdm",
        "market_type": "usd_m_futures",
        "symbol": "BTCUSDT",
        "period": "snapshot",
        "as_of": as_of,
        "endpoint": "order_book_depth",
        "request_class": "order_book_depth",
        "metrics": metrics,
        "units": units,
        "raw_fields": {"snapshotDepthLimit": 20, "bidLevelCount": 20, "askLevelCount": 20},
        "warnings": [],
        "errors": [],
    }


def _availability(
    data_class: str,
    period: str,
    *,
    request_class: str | None = None,
    status: str = "succeeded",
    record_count: int,
    error_count: int = 0,
    reason: str | None = None,
) -> dict[str, Any]:
    record = {
        "data_class": data_class,
        "request_class": request_class or f"{data_class}_history",
        "endpoint": request_class or f"{data_class}_history",
        "symbol": "BTCUSDT",
        "period": period,
        "status": status,
        "record_count": record_count,
        "error_count": error_count,
    }
    if reason:
        record["reason"] = reason
    return record


def _liquidation_availability(*, status: str, reason: str | None = None) -> dict[str, Any]:
    return {
        "data_class": "liquidation_summary",
        "endpoint": "liquidation_order_streams",
        "method": "websocket_market_stream",
        "symbol": "BTCUSDT",
        "period": "source_availability",
        "status": status,
        "record_count": 0,
        "error_count": 0,
        "reason": reason
        or (
            "binance_usdm public liquidation data is real-time WebSocket only; "
            "periodic unauthenticated REST summaries are unavailable"
        ),
        "stream_name": "btcusdt@forceOrder",
        "stream_path": "/market",
        "signed_rest_endpoint": "/fapi/v1/forceOrders",
        "signed_rest_access": "USER_DATA",
        "limitations": [
            "public liquidation stream is real-time and requires a streaming runtime",
            "stream snapshots include only the largest liquidation order within each 1000ms interval",
            "signed REST force-order query is user data and outside public market-data scope",
        ],
        "downstream_implication": "liquidation evidence is unavailable and must not be treated as neutral risk context",
    }


def _write_config(
    tmp_path: Path,
    *,
    data_classes: list[str],
    lookback: int,
) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    data_class_lines = "\n".join(f"      - {data_class}" for data_class in data_classes)
    path = tmp_path / "config.yaml"
    path.write_text(
        f"""
run:
  output_dir: runs
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
  derivatives:
    enabled: true
    source: binance_usdm
    symbols:
      - BTCUSDT
    data_classes:
{data_class_lines}
    periods:
      - 1h
    lookback:
      1h: {lookback}
text:
  enabled: false
report:
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return path


def _context(result) -> dict[str, Any]:
    return json.loads((result.run.analysis_dir / "derivatives_market_context.json").read_text(encoding="utf-8"))


def _manifest(result) -> dict[str, Any]:
    return json.loads(result.run.manifest_path.read_text(encoding="utf-8"))


def _context_record(context: dict[str, Any], *, context_type: str, period: str) -> dict[str, Any]:
    return next(
        record
        for record in context["records"]
        if record["context_type"] == context_type and record["period"] == period
    )


def _noop_stage(config, run) -> list[str]:
    return []
