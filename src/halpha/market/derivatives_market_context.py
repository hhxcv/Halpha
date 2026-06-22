from __future__ import annotations

import json
from datetime import datetime, timezone
from json import JSONDecodeError
from typing import Any

from halpha.data.public_capabilities import DERIVATIVES_CONTEXT_DATA_CLASSES
from halpha.market.derivatives_market_views import load_derivatives_market_view_records
from halpha.runtime.pipeline_contracts import RunContext
from halpha.storage import write_json


STAGE_NAME = "build_derivatives_market_context"
DERIVATIVES_MARKET_CONTEXT_ARTIFACT = "analysis/derivatives_market_context.json"
DERIVATIVES_MARKET_VIEWS_ARTIFACT = "raw/derivatives_market_views.json"
RAW_DERIVATIVES_MARKET_ARTIFACT = "raw/derivatives_market.json"
CONTEXT_SCHEMA_VERSION = 1
STALE_MAX_AGE_HOURS = 48
SUPPORTED_DATA_CLASSES = DERIVATIVES_CONTEXT_DATA_CLASSES

FUNDING_THRESHOLDS = {
    "elevated_positive_funding_rate": 0.0002,
    "extreme_positive_funding_rate": 0.0005,
    "elevated_negative_funding_rate": -0.0002,
    "extreme_negative_funding_rate": -0.0005,
}
OPEN_INTEREST_THRESHOLDS = {
    "expansion_change_pct": 0.05,
    "sharp_expansion_change_pct": 0.15,
    "contraction_change_pct": -0.05,
    "sharp_contraction_change_pct": -0.15,
}
PREMIUM_THRESHOLDS = {
    "stretched_abs_premium_rate": 0.001,
    "stressed_abs_premium_rate": 0.003,
}
BASIS_THRESHOLDS = {
    "stretched_abs_basis_rate": 0.001,
    "stressed_abs_basis_rate": 0.005,
}
SPREAD_DEPTH_THRESHOLDS = {
    "wide_spread_bps": 10.0,
    "stressed_spread_bps": 20.0,
    "depth_imbalance_abs": 0.4,
    "severe_depth_imbalance_abs": 0.7,
}


def build_derivatives_market_context(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    derivatives = _derivatives_config(config)
    if not derivatives.get("enabled"):
        _record_zero_counts(run)
        return []

    created_at = _format_utc(now)
    views, views_error = _read_json(run.raw_dir / "derivatives_market_views.json")
    raw, raw_error = _read_json(run.raw_dir / "derivatives_market.json")
    records: list[dict[str, Any]] = []
    warnings = []
    errors = []
    source_artifacts = [DERIVATIVES_MARKET_VIEWS_ARTIFACT]

    if raw_error is None:
        source_artifacts.append(RAW_DERIVATIVES_MARKET_ARTIFACT)
    if views_error:
        warnings.append(views_error)
    else:
        for view in _list(views.get("views")):
            if not isinstance(view, dict) or view.get("data_class") not in SUPPORTED_DATA_CLASSES:
                continue
            record = _context_record(
                view,
                raw=raw if raw_error is None else {},
                run=run,
                now=created_at,
            )
            records.append(record)
            warnings.extend(_string_list(record.get("warnings")))
            errors.extend(_string_list(record.get("errors")))

    artifact = {
        "schema_version": CONTEXT_SCHEMA_VERSION,
        "artifact_type": "derivatives_market_context",
        "run_id": run.run_id,
        "created_at": created_at,
        "status": _artifact_status(records, warnings=warnings, errors=errors),
        "records": records,
        "counts": _counts(records, warnings=warnings, errors=errors),
        "warnings": _unique_sorted(warnings),
        "errors": errors,
        "source_artifacts": _unique_sorted(source_artifacts),
    }
    write_json(run.analysis_dir / "derivatives_market_context.json", artifact)
    _record_manifest_summary(run, artifact)
    return [DERIVATIVES_MARKET_CONTEXT_ARTIFACT]


def _context_record(
    view: dict[str, Any],
    *,
    raw: dict[str, Any],
    run: RunContext,
    now: str,
) -> dict[str, Any]:
    rows = load_derivatives_market_view_records(view, config_path=run.config_path)
    source_state = _source_state(raw, view)
    status_inputs = _status_inputs(view, rows=rows, source_state=source_state, now=now)
    if view.get("data_class") == "funding_rate":
        state = _funding_state(rows, status_inputs=status_inputs)
        context_type = "funding_pressure"
    elif view.get("data_class") == "open_interest":
        state = _open_interest_state(rows, status_inputs=status_inputs, period=str(view.get("period") or ""))
        context_type = "open_interest_pressure"
    elif view.get("data_class") in {"premium_index", "basis"}:
        state = _premium_basis_state(
            rows,
            raw=raw,
            view=view,
            status_inputs=status_inputs,
        )
        context_type = "premium_basis_state"
    elif view.get("data_class") == "spread_depth":
        state = _spread_depth_state(rows, status_inputs=status_inputs)
        context_type = "liquidity_depth_state"
    else:
        state = _liquidation_availability_state(view, source_state=source_state, status_inputs=status_inputs)
        context_type = "liquidation_availability"

    warnings = _unique_sorted(
        [
            *_string_list(view.get("warnings")),
            *source_state["warnings"],
            *status_inputs["warnings"],
            *state["warnings"],
        ]
    )
    errors = [*source_state["errors"], *state["errors"]]
    source_artifacts = _unique_sorted(
        [
            DERIVATIVES_MARKET_VIEWS_ARTIFACT,
            *_string_list(view.get("source_artifacts")),
        ]
    )
    if source_state["has_raw_source"]:
        source_artifacts.append(RAW_DERIVATIVES_MARKET_ARTIFACT)
        source_artifacts = _unique_sorted(source_artifacts)

    as_of = state["as_of"] or view.get("latest_observation_time")
    record_status = str(status_inputs["status"])
    if state["state"] == "insufficient_evidence" and record_status == "succeeded":
        record_status = "insufficient"
    context_id = _context_id(
        context_type=context_type,
        source=str(view.get("source") or "unknown_source"),
        symbol=str(view.get("symbol") or "unknown_symbol"),
        period=str(view.get("period") or "unknown_period"),
        as_of=str(as_of or "missing"),
    )
    return {
        "context_id": context_id,
        "context_type": context_type,
        "data_class": view.get("data_class"),
        "source": view.get("source"),
        "market_type": view.get("market_type"),
        "symbol": view.get("symbol"),
        "period": view.get("period"),
        "as_of": as_of,
        "status": record_status,
        "state": state["state"],
        "severity": state["severity"],
        "confidence": _confidence(record_status, state["confidence"]),
        "metrics": state["metrics"],
        "thresholds": state["thresholds"],
        "evidence": state["evidence"],
        "uncertainty": _unique_sorted([*status_inputs["uncertainty"], *state["uncertainty"]]),
        "warnings": warnings,
        "errors": errors,
        "source_artifacts": source_artifacts,
    }


def _status_inputs(
    view: dict[str, Any],
    *,
    rows: list[dict[str, Any]],
    source_state: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    warnings = []
    uncertainty = []
    view_status = str(view.get("status") or "unknown")
    latest = view.get("latest_observation_time")
    stale = _is_stale(str(latest), now=now) if isinstance(latest, str) and latest else False
    if stale:
        warnings.append(
            f"{view.get('data_class')} {view.get('symbol')} {view.get('period')} latest observation is stale."
        )
        uncertainty.append("latest derivatives observation is stale.")

    if source_state["status"] in {"failed", "unavailable", "stale", "degraded"} and not rows:
        return {
            "status": source_state["status"],
            "warnings": warnings,
            "uncertainty": [*uncertainty, *source_state["uncertainty"]],
        }
    if view_status in {"missing_history", "skipped"}:
        return {
            "status": "unavailable",
            "warnings": warnings,
            "uncertainty": [*uncertainty, f"view status is {view_status}."],
        }
    if stale:
        return {
            "status": "stale",
            "warnings": warnings,
            "uncertainty": [*uncertainty, *source_state["uncertainty"]],
        }
    if view_status == "insufficient_data":
        return {
            "status": "insufficient",
            "warnings": warnings,
            "uncertainty": [*uncertainty, "view has insufficient derivatives history."],
        }
    if source_state["status"] == "partial":
        return {
            "status": "partial",
            "warnings": warnings,
            "uncertainty": [*uncertainty, *source_state["uncertainty"]],
        }
    return {"status": "succeeded", "warnings": warnings, "uncertainty": uncertainty}


def _funding_state(rows: list[dict[str, Any]], *, status_inputs: dict[str, Any]) -> dict[str, Any]:
    metrics = _metric_series(rows, "funding_rate")
    latest = metrics[-1] if metrics else None
    first = metrics[0] if metrics else None
    latest_row = rows[-1] if rows else {}
    as_of = latest_row.get("as_of") if isinstance(latest_row, dict) else None
    if status_inputs["status"] in {"unavailable", "failed"}:
        return _empty_state("unavailable", thresholds=FUNDING_THRESHOLDS)
    if status_inputs["status"] == "stale":
        return _empty_state("stale", thresholds=FUNDING_THRESHOLDS, as_of=as_of)
    if latest is None:
        return _empty_state(
            "insufficient_evidence",
            thresholds=FUNDING_THRESHOLDS,
            as_of=as_of,
            warnings=["funding_rate metric is missing."],
        )

    change = latest - first if first is not None and len(metrics) >= 2 else None
    state, severity = _funding_pressure_state(latest)
    return {
        "state": state,
        "severity": severity,
        "confidence": "medium",
        "as_of": as_of,
        "metrics": {
            "latest_funding_rate": latest,
            "rolling_funding_rate_change": change,
            "observations": len(metrics),
        },
        "thresholds": FUNDING_THRESHOLDS,
        "evidence": _evidence(
            rows,
            metric_name="funding_rate",
            latest_value=latest,
            rolling_change=change,
        ),
        "uncertainty": [],
        "warnings": [],
        "errors": [],
    }


def _open_interest_state(
    rows: list[dict[str, Any]],
    *,
    status_inputs: dict[str, Any],
    period: str,
) -> dict[str, Any]:
    contracts = _metric_series(rows, "open_interest_contracts")
    latest = contracts[-1] if contracts else None
    first = contracts[0] if contracts else None
    latest_row = rows[-1] if rows else {}
    as_of = latest_row.get("as_of") if isinstance(latest_row, dict) else None
    if status_inputs["status"] in {"unavailable", "failed"}:
        return _empty_state("unavailable", thresholds=OPEN_INTEREST_THRESHOLDS)
    if status_inputs["status"] == "stale":
        return _empty_state("stale", thresholds=OPEN_INTEREST_THRESHOLDS, as_of=as_of)
    if latest is None:
        return _empty_state(
            "insufficient_evidence",
            thresholds=OPEN_INTEREST_THRESHOLDS,
            as_of=as_of,
            warnings=["open_interest_contracts metric is missing."],
        )

    change = latest - first if first is not None and len(contracts) >= 2 else None
    change_pct = change / abs(first) if change is not None and first not in {None, 0} else None
    if change_pct is None:
        state = "open_interest_level_only" if period == "snapshot" else "insufficient_evidence"
        severity = "low" if period == "snapshot" else "unknown"
        confidence = "low"
    else:
        state, severity = _open_interest_pressure_state(change_pct)
        confidence = "medium"
    return {
        "state": state,
        "severity": severity,
        "confidence": confidence,
        "as_of": as_of,
        "metrics": {
            "latest_open_interest_contracts": latest,
            "latest_open_interest_value": _latest_metric(rows, "open_interest_value"),
            "rolling_open_interest_change": change,
            "rolling_open_interest_change_pct": change_pct,
            "observations": len(contracts),
        },
        "thresholds": OPEN_INTEREST_THRESHOLDS,
        "evidence": _evidence(
            rows,
            metric_name="open_interest_contracts",
            latest_value=latest,
            rolling_change=change,
            rolling_change_pct=change_pct,
        ),
        "uncertainty": [] if change_pct is not None else ["open interest has no rolling change window."],
        "warnings": [],
        "errors": [],
    }


def _premium_basis_state(
    rows: list[dict[str, Any]],
    *,
    raw: dict[str, Any],
    view: dict[str, Any],
    status_inputs: dict[str, Any],
) -> dict[str, Any]:
    data_class = str(view.get("data_class") or "")
    if data_class == "premium_index":
        return _premium_state(rows, status_inputs=status_inputs)
    return _basis_state(rows, raw=raw, view=view, status_inputs=status_inputs)


def _spread_depth_state(rows: list[dict[str, Any]], *, status_inputs: dict[str, Any]) -> dict[str, Any]:
    latest_spread_bps = _latest_metric(rows, "spread_bps")
    latest_imbalance = _latest_metric(rows, "depth_imbalance")
    latest_row = rows[-1] if rows else {}
    as_of = latest_row.get("as_of") if isinstance(latest_row, dict) else None
    if status_inputs["status"] in {"unavailable", "failed"}:
        return _empty_state("unavailable", thresholds=SPREAD_DEPTH_THRESHOLDS)
    if status_inputs["status"] == "stale":
        return _empty_state("stale", thresholds=SPREAD_DEPTH_THRESHOLDS, as_of=as_of)
    if latest_spread_bps is None or latest_imbalance is None:
        missing = "spread_bps" if latest_spread_bps is None else "depth_imbalance"
        return _empty_state(
            "insufficient_evidence",
            thresholds=SPREAD_DEPTH_THRESHOLDS,
            as_of=as_of,
            warnings=[f"{missing} metric is missing."],
        )
    state, severity = _spread_depth_state_from_metrics(latest_spread_bps, latest_imbalance)
    return {
        "state": state,
        "severity": severity,
        "confidence": "medium",
        "as_of": as_of,
        "metrics": {
            "top_bid_price": _latest_metric(rows, "top_bid_price"),
            "top_ask_price": _latest_metric(rows, "top_ask_price"),
            "mid_price": _latest_metric(rows, "mid_price"),
            "spread": _latest_metric(rows, "spread"),
            "spread_bps": latest_spread_bps,
            "bid_depth_quantity": _latest_metric(rows, "bid_depth_quantity"),
            "ask_depth_quantity": _latest_metric(rows, "ask_depth_quantity"),
            "bid_depth_notional": _latest_metric(rows, "bid_depth_notional"),
            "ask_depth_notional": _latest_metric(rows, "ask_depth_notional"),
            "depth_imbalance": latest_imbalance,
            "snapshot_depth_limit": _latest_metric(rows, "snapshot_depth_limit"),
            "observations": len(_metric_series(rows, "spread_bps")),
            "units": _latest_units(rows),
        },
        "thresholds": SPREAD_DEPTH_THRESHOLDS,
        "evidence": _evidence(
            rows,
            metric_name="spread_bps",
            latest_value=latest_spread_bps,
            rolling_change=None,
        ),
        "uncertainty": ["single depth snapshot is not execution-grade liquidity evidence."],
        "warnings": [],
        "errors": [],
    }


def _liquidation_availability_state(
    view: dict[str, Any],
    *,
    source_state: dict[str, Any],
    status_inputs: dict[str, Any],
) -> dict[str, Any]:
    status = str(status_inputs["status"])
    availability = [item for item in _list(source_state.get("availability")) if isinstance(item, dict)]
    state = "unavailable" if status in {"failed", "unavailable"} else status
    if state == "succeeded":
        state = "insufficient_evidence"
    warnings = [
        "periodic public liquidation summary is unavailable for the configured source."
        if state == "unavailable"
        else f"liquidation source availability is {state}."
    ]
    return {
        "state": state,
        "severity": "unknown" if state in {"unavailable", "insufficient_evidence"} else "medium",
        "confidence": "low",
        "as_of": view.get("latest_observation_time"),
        "metrics": {
            "available_periodic_public_summary": False,
            "availability_records": len(availability),
        },
        "thresholds": {},
        "evidence": [_liquidation_availability_evidence(item) for item in availability],
        "uncertainty": [
            "missing liquidation evidence must not lower risk.",
            "websocket liquidation streams require a runtime outside the current periodic pipeline.",
        ],
        "warnings": warnings,
        "errors": [],
    }


def _premium_state(rows: list[dict[str, Any]], *, status_inputs: dict[str, Any]) -> dict[str, Any]:
    latest = _latest_metric(rows, "premium_rate")
    latest_row = rows[-1] if rows else {}
    as_of = latest_row.get("as_of") if isinstance(latest_row, dict) else None
    if status_inputs["status"] in {"unavailable", "failed"}:
        return _empty_state("unavailable", thresholds=PREMIUM_THRESHOLDS)
    if status_inputs["status"] == "stale":
        return _empty_state("stale", thresholds=PREMIUM_THRESHOLDS, as_of=as_of)
    if latest is None:
        return _empty_state(
            "insufficient_evidence",
            thresholds=PREMIUM_THRESHOLDS,
            as_of=as_of,
            warnings=["premium_rate metric is missing."],
        )
    state, severity = _premium_state_from_rate(latest)
    return {
        "state": state,
        "severity": severity,
        "confidence": "medium",
        "as_of": as_of,
        "metrics": {
            "latest_premium_rate": latest,
            "latest_mark_price": _latest_metric(rows, "mark_price"),
            "latest_index_price": _latest_metric(rows, "index_price"),
            "latest_last_funding_rate": _latest_metric(rows, "last_funding_rate"),
            "latest_interest_rate": _latest_metric(rows, "interest_rate"),
            "observations": len(_metric_series(rows, "premium_rate")),
            "units": _latest_units(rows),
        },
        "thresholds": PREMIUM_THRESHOLDS,
        "evidence": _evidence(
            rows,
            metric_name="premium_rate",
            latest_value=latest,
            rolling_change=None,
        ),
        "uncertainty": [],
        "warnings": [],
        "errors": [],
    }


def _basis_state(
    rows: list[dict[str, Any]],
    *,
    raw: dict[str, Any],
    view: dict[str, Any],
    status_inputs: dict[str, Any],
) -> dict[str, Any]:
    latest = _latest_metric(rows, "basis_rate")
    latest_row = rows[-1] if rows else {}
    as_of = latest_row.get("as_of") if isinstance(latest_row, dict) else None
    if status_inputs["status"] in {"unavailable", "failed"}:
        return _empty_state("unavailable", thresholds=BASIS_THRESHOLDS)
    if status_inputs["status"] == "stale":
        return _empty_state("stale", thresholds=BASIS_THRESHOLDS, as_of=as_of)
    if latest is None:
        return _empty_state(
            "insufficient_evidence",
            thresholds=BASIS_THRESHOLDS,
            as_of=as_of,
            warnings=["basis_rate metric is missing."],
        )
    state, severity = _basis_state_from_rate(latest)
    contract_type = _raw_field_for_as_of(raw, view, as_of, "contractType")
    return {
        "state": state,
        "severity": severity,
        "confidence": "medium",
        "as_of": as_of,
        "metrics": {
            "latest_basis": _latest_metric(rows, "basis"),
            "latest_basis_rate": latest,
            "latest_annualized_basis_rate": _latest_metric(rows, "annualized_basis_rate"),
            "latest_futures_price": _latest_metric(rows, "futures_price"),
            "latest_index_price": _latest_metric(rows, "index_price"),
            "contract_type": contract_type,
            "observations": len(_metric_series(rows, "basis_rate")),
            "units": _latest_units(rows),
        },
        "thresholds": BASIS_THRESHOLDS,
        "evidence": _evidence(
            rows,
            metric_name="basis_rate",
            latest_value=latest,
            rolling_change=None,
        ),
        "uncertainty": [],
        "warnings": [],
        "errors": [],
    }


def _source_state(raw: dict[str, Any], view: dict[str, Any]) -> dict[str, Any]:
    has_raw_source = bool(raw)
    availability = [
        item
        for item in _list(raw.get("availability"))
        if isinstance(item, dict) and _availability_matches(item, view)
    ]
    raw_errors = [
        item
        for item in _list(raw.get("errors"))
        if isinstance(item, dict) and _availability_matches(item, view)
    ]
    statuses = {str(item.get("status")) for item in availability if isinstance(item.get("status"), str)}
    warnings = []
    errors = []
    uncertainty = []
    for item in availability:
        status = item.get("status")
        if status in {"partial", "failed", "unavailable", "stale", "degraded"}:
            reason = item.get("reason") or status
            warnings.append(
                f"derivatives source availability is {status} for {view.get('data_class')} "
                f"{view.get('symbol')} {view.get('period')}: {reason}."
            )
            uncertainty.append(f"source availability is {status}.")
    for item in raw_errors:
        message = item.get("message")
        if isinstance(message, str) and message:
            errors.append(message)
    if "failed" in statuses:
        status = "failed"
    elif "unavailable" in statuses:
        status = "unavailable"
    elif "stale" in statuses:
        status = "stale"
    elif "degraded" in statuses:
        status = "degraded"
    elif "partial" in statuses or raw_errors:
        status = "partial"
    else:
        status = "succeeded"
    return {
        "status": status,
        "warnings": _unique_sorted(warnings),
        "errors": errors,
        "uncertainty": _unique_sorted(uncertainty),
        "has_raw_source": has_raw_source,
        "availability": availability,
    }


def _availability_matches(item: dict[str, Any], view: dict[str, Any]) -> bool:
    if item.get("data_class") != view.get("data_class"):
        return False
    for key in ("symbol", "period"):
        value = item.get(key)
        if value is not None and view.get(key) is not None and value != view.get(key):
            return False
    return True


def _funding_pressure_state(latest: float) -> tuple[str, str]:
    if latest >= FUNDING_THRESHOLDS["extreme_positive_funding_rate"]:
        return "extreme_positive_funding", "high"
    if latest >= FUNDING_THRESHOLDS["elevated_positive_funding_rate"]:
        return "elevated_positive_funding", "medium"
    if latest <= FUNDING_THRESHOLDS["extreme_negative_funding_rate"]:
        return "extreme_negative_funding", "high"
    if latest <= FUNDING_THRESHOLDS["elevated_negative_funding_rate"]:
        return "elevated_negative_funding", "medium"
    return "neutral", "low"


def _open_interest_pressure_state(change_pct: float) -> tuple[str, str]:
    if change_pct >= OPEN_INTEREST_THRESHOLDS["sharp_expansion_change_pct"]:
        return "sharp_open_interest_expansion", "high"
    if change_pct >= OPEN_INTEREST_THRESHOLDS["expansion_change_pct"]:
        return "open_interest_expansion", "medium"
    if change_pct <= OPEN_INTEREST_THRESHOLDS["sharp_contraction_change_pct"]:
        return "sharp_open_interest_contraction", "high"
    if change_pct <= OPEN_INTEREST_THRESHOLDS["contraction_change_pct"]:
        return "open_interest_contraction", "medium"
    return "neutral", "low"


def _premium_state_from_rate(latest: float) -> tuple[str, str]:
    absolute = abs(latest)
    if latest < 0:
        severity = "high" if absolute >= PREMIUM_THRESHOLDS["stressed_abs_premium_rate"] else "medium"
        return "premium_inverted", severity
    if absolute >= PREMIUM_THRESHOLDS["stressed_abs_premium_rate"]:
        return "premium_stressed", "high"
    if absolute >= PREMIUM_THRESHOLDS["stretched_abs_premium_rate"]:
        return "premium_stretched", "medium"
    return "neutral", "low"


def _basis_state_from_rate(latest: float) -> tuple[str, str]:
    absolute = abs(latest)
    if latest < 0:
        severity = "high" if absolute >= BASIS_THRESHOLDS["stressed_abs_basis_rate"] else "medium"
        return "basis_inverted", severity
    if absolute >= BASIS_THRESHOLDS["stressed_abs_basis_rate"]:
        return "basis_stressed", "high"
    if absolute >= BASIS_THRESHOLDS["stretched_abs_basis_rate"]:
        return "basis_stretched", "medium"
    return "neutral", "low"


def _spread_depth_state_from_metrics(spread_bps: float, imbalance: float) -> tuple[str, str]:
    if spread_bps >= SPREAD_DEPTH_THRESHOLDS["stressed_spread_bps"]:
        return "spread_stressed", "high"
    if spread_bps >= SPREAD_DEPTH_THRESHOLDS["wide_spread_bps"]:
        return "spread_wide", "medium"
    imbalance_abs = abs(imbalance)
    if imbalance_abs >= SPREAD_DEPTH_THRESHOLDS["severe_depth_imbalance_abs"]:
        return "depth_imbalanced", "high"
    if imbalance_abs >= SPREAD_DEPTH_THRESHOLDS["depth_imbalance_abs"]:
        return "depth_imbalanced", "medium"
    return "neutral", "low"


def _empty_state(
    state: str,
    *,
    thresholds: dict[str, float],
    as_of: Any = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    severity = "unknown" if state in {"insufficient_evidence", "unavailable"} else "medium"
    return {
        "state": state,
        "severity": severity,
        "confidence": "low",
        "as_of": as_of,
        "metrics": {},
        "thresholds": thresholds,
        "evidence": [],
        "uncertainty": [f"{state} prevents deterministic derivatives context."],
        "warnings": warnings or [],
        "errors": [],
    }


def _evidence(
    rows: list[dict[str, Any]],
    *,
    metric_name: str,
    latest_value: float,
    rolling_change: float | None,
    rolling_change_pct: float | None = None,
) -> list[dict[str, Any]]:
    latest_row = rows[-1] if rows else {}
    evidence = [
        {
            "metric": metric_name,
            "value": latest_value,
            "as_of": latest_row.get("as_of") if isinstance(latest_row, dict) else None,
            "source_artifact": DERIVATIVES_MARKET_VIEWS_ARTIFACT,
        }
    ]
    if rolling_change is not None:
        evidence.append(
            {
                "metric": f"{metric_name}_rolling_change",
                "value": rolling_change,
                "window_start": rows[0].get("as_of") if rows and isinstance(rows[0], dict) else None,
                "window_end": latest_row.get("as_of") if isinstance(latest_row, dict) else None,
                "source_artifact": DERIVATIVES_MARKET_VIEWS_ARTIFACT,
            }
        )
    if rolling_change_pct is not None:
        evidence.append(
            {
                "metric": f"{metric_name}_rolling_change_pct",
                "value": rolling_change_pct,
                "window_start": rows[0].get("as_of") if rows and isinstance(rows[0], dict) else None,
                "window_end": latest_row.get("as_of") if isinstance(latest_row, dict) else None,
                "source_artifact": DERIVATIVES_MARKET_VIEWS_ARTIFACT,
            }
        )
    return evidence


def _liquidation_availability_evidence(item: dict[str, Any]) -> dict[str, Any]:
    evidence = {
        "source_artifact": RAW_DERIVATIVES_MARKET_ARTIFACT,
        "status": item.get("status"),
        "endpoint": item.get("endpoint"),
        "method": item.get("method"),
        "reason": item.get("reason"),
        "symbol": item.get("symbol"),
        "period": item.get("period"),
    }
    for key in (
        "stream_name",
        "stream_path",
        "signed_rest_endpoint",
        "signed_rest_access",
        "limitations",
        "downstream_implication",
    ):
        if key in item:
            evidence[key] = item[key]
    return {key: value for key, value in evidence.items() if value is not None}


def _metric_series(rows: list[dict[str, Any]], metric_name: str) -> list[float]:
    values = []
    for row in rows:
        value = _metric(row, metric_name)
        if value is not None:
            values.append(value)
    return values


def _latest_metric(rows: list[dict[str, Any]], metric_name: str) -> float | None:
    for row in reversed(rows):
        value = _metric(row, metric_name)
        if value is not None:
            return value
    return None


def _latest_units(rows: list[dict[str, Any]]) -> dict[str, Any]:
    for row in reversed(rows):
        units = row.get("units") if isinstance(row, dict) else None
        if isinstance(units, dict):
            return dict(sorted(units.items()))
    return {}


def _metric(row: dict[str, Any], metric_name: str) -> float | None:
    metrics = row.get("metrics") if isinstance(row, dict) else None
    if not isinstance(metrics, dict):
        return None
    value = metrics.get(metric_name)
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _raw_field_for_as_of(raw: dict[str, Any], view: dict[str, Any], as_of: Any, field: str) -> Any:
    for item in _list(raw.get("items")):
        if not isinstance(item, dict):
            continue
        if item.get("data_class") != view.get("data_class"):
            continue
        if item.get("symbol") != view.get("symbol") or item.get("period") != view.get("period"):
            continue
        if as_of is not None and item.get("as_of") != as_of:
            continue
        raw_fields = item.get("raw_fields")
        if isinstance(raw_fields, dict) and field in raw_fields:
            return raw_fields[field]
    return None


def _confidence(status: str, base: str) -> str:
    if status == "succeeded":
        return base
    if status == "partial" and base == "medium":
        return "low"
    return "low"


def _context_id(*, context_type: str, source: str, symbol: str, period: str, as_of: str) -> str:
    return f"derivatives_context:{context_type}:{source}:{symbol}:{period}:{as_of}"


def _is_stale(value: str, *, now: str) -> bool:
    parsed = _parse_utc(value)
    now_value = _parse_utc(now)
    if parsed is None or now_value is None:
        return False
    age_hours = (now_value - parsed).total_seconds() / 3600
    return age_hours > STALE_MAX_AGE_HOURS


def _read_json(path) -> tuple[dict[str, Any], str | None]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, f"{path.name} was not found."
    except JSONDecodeError as exc:
        return {}, f"{path.name} is not valid JSON: {exc.msg}."
    if not isinstance(loaded, dict):
        return {}, f"{path.name} must be a JSON object."
    return loaded, None


def _record_manifest_summary(run: RunContext, artifact: dict[str, Any]) -> None:
    counts = artifact["counts"]
    run.manifest["artifacts"]["derivatives_market_context"] = DERIVATIVES_MARKET_CONTEXT_ARTIFACT
    run.manifest["derivatives_market_context"] = {
        "status": artifact["status"],
        "artifact": DERIVATIVES_MARKET_CONTEXT_ARTIFACT,
        "records": counts["records"],
        "funding_pressure": counts["funding_pressure"],
        "open_interest_pressure": counts["open_interest_pressure"],
        "premium_basis_state": counts["premium_basis_state"],
        "liquidity_depth_state": counts["liquidity_depth_state"],
        "liquidation_availability": counts["liquidation_availability"],
        "warnings": counts["warnings"],
        "errors": counts["errors"],
        "states": counts["states"],
        "severities": counts["severities"],
        "statuses": counts["statuses"],
    }
    manifest_counts = run.manifest.setdefault("counts", {})
    manifest_counts["derivatives_market_context_records"] = counts["records"]
    manifest_counts["derivatives_market_context_funding_pressure"] = counts["funding_pressure"]
    manifest_counts["derivatives_market_context_open_interest_pressure"] = counts["open_interest_pressure"]
    manifest_counts["derivatives_market_context_premium_basis_state"] = counts["premium_basis_state"]
    manifest_counts["derivatives_market_context_liquidity_depth_state"] = counts["liquidity_depth_state"]
    manifest_counts["derivatives_market_context_liquidation_availability"] = counts["liquidation_availability"]
    manifest_counts["derivatives_market_context_warnings"] = counts["warnings"]
    manifest_counts["derivatives_market_context_errors"] = counts["errors"]


def _record_zero_counts(run: RunContext) -> None:
    counts = run.manifest.setdefault("counts", {})
    counts["derivatives_market_context_records"] = 0
    counts["derivatives_market_context_funding_pressure"] = 0
    counts["derivatives_market_context_open_interest_pressure"] = 0
    counts["derivatives_market_context_premium_basis_state"] = 0
    counts["derivatives_market_context_liquidity_depth_state"] = 0
    counts["derivatives_market_context_liquidation_availability"] = 0
    counts["derivatives_market_context_warnings"] = 0
    counts["derivatives_market_context_errors"] = 0


def _counts(records: list[dict[str, Any]], *, warnings: list[str], errors: list[str]) -> dict[str, Any]:
    return {
        "records": len(records),
        "funding_pressure": sum(1 for record in records if record.get("context_type") == "funding_pressure"),
        "open_interest_pressure": sum(
            1 for record in records if record.get("context_type") == "open_interest_pressure"
        ),
        "premium_basis_state": sum(1 for record in records if record.get("context_type") == "premium_basis_state"),
        "liquidity_depth_state": sum(
            1 for record in records if record.get("context_type") == "liquidity_depth_state"
        ),
        "liquidation_availability": sum(
            1 for record in records if record.get("context_type") == "liquidation_availability"
        ),
        "succeeded": sum(1 for record in records if record.get("status") == "succeeded"),
        "partial": sum(1 for record in records if record.get("status") == "partial"),
        "stale": sum(1 for record in records if record.get("status") == "stale"),
        "insufficient": sum(1 for record in records if record.get("status") == "insufficient"),
        "unavailable": sum(1 for record in records if record.get("status") == "unavailable"),
        "failed": sum(1 for record in records if record.get("status") == "failed"),
        "states": _value_counts(records, "state"),
        "severities": _value_counts(records, "severity"),
        "statuses": _value_counts(records, "status"),
        "warnings": len(_unique_sorted(warnings)),
        "errors": len(errors),
    }


def _value_counts(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = record.get(field)
        if not isinstance(value, str) or not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _artifact_status(records: list[dict[str, Any]], *, warnings: list[str], errors: list[str]) -> str:
    if errors and not records:
        return "failed"
    if not records:
        return "warning" if warnings or errors else "skipped"
    statuses = {str(record.get("status")) for record in records}
    if statuses == {"succeeded"} and not warnings and not errors:
        return "ok"
    return "warning"


def _derivatives_config(config: dict[str, Any]) -> dict[str, Any]:
    market = config.get("market")
    if not isinstance(market, dict):
        return {}
    derivatives = market.get("derivatives")
    return derivatives if isinstance(derivatives, dict) else {}


def _parse_utc(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("created_at must include a UTC offset.")
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        parsed = _parse_utc(value)
        if parsed is None:
            raise ValueError("created_at must be an ISO 8601 UTC string.")
        timestamp = parsed.replace(microsecond=0)
    else:
        raise ValueError("created_at must be a datetime or ISO 8601 UTC string.")
    return timestamp.isoformat().replace("+00:00", "Z")


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value or [] if isinstance(item, str) and item]


def _unique_sorted(values: list[str]) -> list[str]:
    return sorted({value for value in values if value})
