from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from halpha.config import load_config
from halpha.derivatives_history import sync_derivatives_market_history
from halpha.derivatives_market_context import build_derivatives_market_context
from halpha.derivatives_market_views import build_derivatives_market_views
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


def _write_config(
    tmp_path: Path,
    *,
    data_classes: list[str],
    lookback: int,
) -> Path:
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
