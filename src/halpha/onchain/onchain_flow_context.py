from __future__ import annotations

import json
from datetime import datetime, timezone
from json import JSONDecodeError
from typing import Any

from halpha.data.public_capabilities import ONCHAIN_FLOW_CONTEXT_DATA_CLASSES
from halpha.runtime.pipeline_contracts import RunContext
from halpha.storage import write_json


STAGE_NAME = "build_onchain_flow_context"
ONCHAIN_FLOW_CONTEXT_ARTIFACT = "analysis/onchain_flow_context.json"
ONCHAIN_FLOW_VIEWS_ARTIFACT = "raw/onchain_flow_views.json"
RAW_ONCHAIN_FLOW_ARTIFACT = "raw/onchain_flow.json"
CONTEXT_SCHEMA_VERSION = 1
STALE_MAX_AGE_HOURS = 72
SUPPORTED_DATA_CLASSES = ONCHAIN_FLOW_CONTEXT_DATA_CLASSES

STABLECOIN_THRESHOLDS = {
    "supply_expansion_change_pct": 0.02,
    "sharp_supply_expansion_change_pct": 0.05,
    "supply_contraction_change_pct": -0.02,
    "sharp_supply_contraction_change_pct": -0.05,
}
CHAIN_ACTIVITY_THRESHOLDS = {
    "elevated_activity_change_pct": 0.20,
    "surging_activity_change_pct": 0.50,
    "depressed_activity_change_pct": -0.20,
    "sharply_depressed_activity_change_pct": -0.50,
}
NETWORK_CONGESTION_THRESHOLDS = {
    "elevated_mempool_size_bytes": 20_000_000.0,
    "severe_mempool_size_bytes": 100_000_000.0,
    "elevated_mempool_change_pct": 0.50,
    "severe_mempool_change_pct": 2.00,
}
EXCHANGE_FLOW_THRESHOLDS = {
    "reliable_periodic_public_source_required": True,
}


def build_onchain_flow_context(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    onchain_flow = _onchain_flow_config(config)
    if not onchain_flow.get("enabled"):
        _record_zero_counts(run)
        return []

    created_at = _format_utc(now)
    views, views_error = _read_json(run.raw_dir / "onchain_flow_views.json")
    raw, raw_error = _read_json(run.raw_dir / "onchain_flow.json")
    records: list[dict[str, Any]] = []
    warnings = []
    errors: list[dict[str, Any]] = []
    source_artifacts = [ONCHAIN_FLOW_VIEWS_ARTIFACT]

    if raw_error is None:
        source_artifacts.append(RAW_ONCHAIN_FLOW_ARTIFACT)
    if views_error:
        warnings.append(views_error)
    else:
        for view in _list(views.get("views")):
            if not isinstance(view, dict) or view.get("data_class") not in SUPPORTED_DATA_CLASSES:
                continue
            record = _context_record(
                view,
                raw=raw if raw_error is None else {},
                now=created_at,
            )
            records.append(record)
            warnings.extend(_string_list(record.get("warnings")))
            errors.extend(_error_list(record.get("errors")))

    artifact = {
        "schema_version": CONTEXT_SCHEMA_VERSION,
        "artifact_type": "onchain_flow_context",
        "run_id": run.run_id,
        "created_at": created_at,
        "status": _artifact_status(records, warnings=warnings, errors=errors),
        "records": sorted(records, key=lambda record: _record_sort_key(record)),
        "counts": _counts(records, warnings=warnings, errors=errors),
        "warnings": _unique_sorted(warnings),
        "errors": errors,
        "source_artifacts": _unique_sorted(source_artifacts),
    }
    write_json(run.analysis_dir / "onchain_flow_context.json", artifact)
    _record_manifest_summary(run, artifact)
    return [ONCHAIN_FLOW_CONTEXT_ARTIFACT]


def _context_record(
    view: dict[str, Any],
    *,
    raw: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    rows = _view_records(view)
    source_state = _source_state(raw, view)
    status_inputs = _status_inputs(view, rows=rows, source_state=source_state, now=now)
    data_class = str(view.get("data_class") or "")
    if data_class == "stablecoin_supply":
        state = _stablecoin_state(rows, status_inputs=status_inputs)
        context_type = "stablecoin_liquidity"
    elif data_class == "chain_activity":
        state = _chain_activity_state(rows, status_inputs=status_inputs)
        context_type = "chain_activity"
    elif data_class == "network_congestion":
        state = _network_congestion_state(rows, status_inputs=status_inputs)
        context_type = "network_congestion"
    else:
        state = _exchange_flow_availability_state(view, source_state=source_state, status_inputs=status_inputs)
        context_type = "exchange_flow_source_availability"

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
            ONCHAIN_FLOW_VIEWS_ARTIFACT,
            *_string_list(view.get("source_artifacts")),
        ]
    )
    if source_state["has_raw_source"]:
        source_artifacts.append(RAW_ONCHAIN_FLOW_ARTIFACT)
        source_artifacts = _unique_sorted(source_artifacts)

    as_of = state["as_of"] or view.get("latest_observation_time")
    status = str(status_inputs["status"])
    if state["state"] == "insufficient_evidence" and status in {"succeeded", "bounded"}:
        status = "insufficient"
    return {
        "context_id": _context_id(
            context_type=context_type,
            source=str(view.get("source") or "unknown_source"),
            asset=str(view.get("asset") or "unknown_asset"),
            chain=str(view.get("chain") or "unknown_chain"),
            as_of=str(as_of or view.get("input_window_end") or "missing"),
        ),
        "context_type": context_type,
        "data_class": view.get("data_class"),
        "source": view.get("source"),
        "asset": view.get("asset"),
        "chain": view.get("chain"),
        "as_of": as_of,
        "status": status,
        "state": state["state"],
        "severity": state["severity"],
        "confidence": _confidence(status, state["confidence"]),
        "source_availability": source_state["status"],
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
        warnings.append(f"{view.get('data_class')} latest on-chain flow observation is stale.")
        uncertainty.append("latest on-chain flow observation is stale.")

    if view_status in {"failed", "insufficient_data", "missing_availability", "missing_history", "skipped", "stale", "unavailable"} and not rows:
        status = "insufficient" if view_status == "insufficient_data" else view_status
        return {
            "status": status,
            "warnings": warnings,
            "uncertainty": [*uncertainty, f"view status is {view_status}.", *source_state["uncertainty"]],
        }
    if stale:
        return {
            "status": "stale",
            "warnings": warnings,
            "uncertainty": [*uncertainty, *source_state["uncertainty"]],
        }
    if view_status == "partial" or source_state["status"] == "partial":
        return {
            "status": "partial",
            "warnings": warnings,
            "uncertainty": [*uncertainty, "source availability is partial.", *source_state["uncertainty"]],
        }
    if view_status == "bounded":
        return {
            "status": "bounded",
            "warnings": warnings,
            "uncertainty": [*uncertainty, "view records were bounded and may omit older current-window rows."],
        }
    return {"status": "succeeded", "warnings": warnings, "uncertainty": uncertainty}


def _stablecoin_state(rows: list[dict[str, Any]], *, status_inputs: dict[str, Any]) -> dict[str, Any]:
    if status_inputs["status"] in {"failed", "missing_availability", "missing_history", "skipped", "stale", "unavailable"}:
        return _empty_state(str(status_inputs["status"]), thresholds=STABLECOIN_THRESHOLDS, rows=rows)
    metrics = _metric_series(rows, "total_circulating_usd") or _metric_series(rows, "total_circulating")
    if len(metrics) < 2:
        return _empty_state(
            "insufficient_evidence",
            thresholds=STABLECOIN_THRESHOLDS,
            rows=rows,
            warnings=["stablecoin supply context requires at least two observations."],
        )
    first = metrics[0]
    latest = metrics[-1]
    change = latest - first
    change_pct = _safe_change_pct(first, latest)
    state, severity = _stablecoin_state_from_change(change_pct)
    return {
        "state": state,
        "severity": severity,
        "confidence": "medium",
        "as_of": rows[-1].get("as_of"),
        "metrics": {
            "first_stablecoin_supply": first,
            "latest_stablecoin_supply": latest,
            "stablecoin_supply_change": change,
            "stablecoin_supply_change_pct": change_pct,
            "observations": len(metrics),
            "units": _latest_units(rows),
        },
        "thresholds": STABLECOIN_THRESHOLDS,
        "evidence": _evidence(rows, metric_name="stablecoin_supply", latest_value=latest, rolling_change=change, rolling_change_pct=change_pct),
        "uncertainty": [
            "stablecoin supply is liquidity context, not a price forecast.",
            "supply changes can reflect issuance, redemption, or source methodology timing.",
        ],
        "warnings": [],
        "errors": [],
    }


def _chain_activity_state(rows: list[dict[str, Any]], *, status_inputs: dict[str, Any]) -> dict[str, Any]:
    if status_inputs["status"] in {"failed", "missing_availability", "missing_history", "skipped", "stale", "unavailable"}:
        return _empty_state(str(status_inputs["status"]), thresholds=CHAIN_ACTIVITY_THRESHOLDS, rows=rows)
    transaction_points = _metric_points(rows, "transaction_count")
    if len(transaction_points) < 2:
        return _empty_state(
            "insufficient_evidence",
            thresholds=CHAIN_ACTIVITY_THRESHOLDS,
            rows=rows,
            warnings=["chain activity context requires at least two observations."],
        )
    first = transaction_points[0]["value"]
    latest = transaction_points[-1]["value"]
    change = latest - first
    change_pct = _safe_change_pct(first, latest)
    state, severity = _chain_activity_state_from_change(change_pct)
    transfer_volume_points = _metric_points(rows, "estimated_transaction_volume_btc")
    transfer_volume_metrics = _optional_change_metrics(
        transfer_volume_points,
        first_key="first_estimated_transaction_volume_btc",
        latest_key="latest_estimated_transaction_volume_btc",
        change_key="estimated_transaction_volume_btc_change",
        change_pct_key="estimated_transaction_volume_btc_change_pct",
        observations_key="estimated_transaction_volume_observations",
    )
    evidence = _metric_evidence(
        transaction_points,
        metric_name="transaction_count",
        latest_value=latest,
        rolling_change=change,
        rolling_change_pct=change_pct,
    )
    if transfer_volume_points:
        evidence.extend(
            _metric_evidence(
                transfer_volume_points,
                metric_name="estimated_transaction_volume_btc",
                latest_value=transfer_volume_points[-1]["value"],
                rolling_change=transfer_volume_metrics.get("estimated_transaction_volume_btc_change"),
                rolling_change_pct=transfer_volume_metrics.get("estimated_transaction_volume_btc_change_pct"),
            )
        )
    return {
        "state": state,
        "severity": severity,
        "confidence": "medium",
        "as_of": transaction_points[-1]["as_of"],
        "metrics": {
            "first_transaction_count": first,
            "latest_transaction_count": latest,
            "transaction_count_change": change,
            "transaction_count_change_pct": change_pct,
            "transaction_count_observations": len(transaction_points),
            **transfer_volume_metrics,
            "units": _latest_units(rows),
        },
        "thresholds": CHAIN_ACTIVITY_THRESHOLDS,
        "evidence": evidence,
        "uncertainty": [
            "chain activity is usage context, not a directional price signal.",
            "estimated transaction volume is not the same as exchange netflow or economic demand.",
        ],
        "warnings": [],
        "errors": [],
    }


def _network_congestion_state(rows: list[dict[str, Any]], *, status_inputs: dict[str, Any]) -> dict[str, Any]:
    if status_inputs["status"] in {"failed", "missing_availability", "missing_history", "skipped", "stale", "unavailable"}:
        return _empty_state(str(status_inputs["status"]), thresholds=NETWORK_CONGESTION_THRESHOLDS, rows=rows)
    mempool_size_points = _metric_points(rows, "mempool_size_bytes")
    if not mempool_size_points:
        return _empty_state(
            "insufficient_evidence",
            thresholds=NETWORK_CONGESTION_THRESHOLDS,
            rows=rows,
            warnings=["network congestion context requires mempool_size_bytes observations."],
        )
    first = mempool_size_points[0]["value"]
    latest = mempool_size_points[-1]["value"]
    change = latest - first if len(mempool_size_points) >= 2 else None
    change_pct = _safe_change_pct(first, latest) if len(mempool_size_points) >= 2 else None
    state, severity = _network_congestion_state_from_metrics(latest, change_pct)
    mempool_count_points = _metric_points(rows, "mempool_transaction_count")
    mempool_count_metrics = _optional_change_metrics(
        mempool_count_points,
        first_key="first_mempool_transaction_count",
        latest_key="latest_mempool_transaction_count",
        change_key="mempool_transaction_count_change",
        change_pct_key="mempool_transaction_count_change_pct",
        observations_key="mempool_transaction_count_observations",
    )
    evidence = _metric_evidence(
        mempool_size_points,
        metric_name="mempool_size_bytes",
        latest_value=latest,
        rolling_change=change,
        rolling_change_pct=change_pct,
    )
    if mempool_count_points:
        evidence.extend(
            _metric_evidence(
                mempool_count_points,
                metric_name="mempool_transaction_count",
                latest_value=mempool_count_points[-1]["value"],
                rolling_change=mempool_count_metrics.get("mempool_transaction_count_change"),
                rolling_change_pct=mempool_count_metrics.get("mempool_transaction_count_change_pct"),
            )
        )
    return {
        "state": state,
        "severity": severity,
        "confidence": "medium",
        "as_of": mempool_size_points[-1]["as_of"],
        "metrics": {
            "latest_mempool_size_bytes": latest,
            "mempool_size_change": change,
            "mempool_size_change_pct": change_pct,
            "mempool_size_observations": len(mempool_size_points),
            **mempool_count_metrics,
            "units": _latest_units(rows),
        },
        "thresholds": NETWORK_CONGESTION_THRESHOLDS,
        "evidence": evidence,
        "uncertainty": [
            "network congestion is settlement-friction context, not a price forecast.",
            "mempool transaction count and mempool size can diverge when average transaction weight changes.",
        ],
        "warnings": [],
        "errors": [],
    }


def _exchange_flow_availability_state(
    view: dict[str, Any],
    *,
    source_state: dict[str, Any],
    status_inputs: dict[str, Any],
) -> dict[str, Any]:
    status = str(status_inputs["status"])
    if status == "succeeded":
        state = "source_available"
        severity = "low"
        uncertainty = ["source availability does not imply exchange-flow pressure by itself."]
    elif status == "failed":
        state = "source_failed"
        severity = "medium"
        uncertainty = ["failed exchange-flow source prevents deterministic exchange-flow context."]
    elif status == "unavailable":
        state = "source_unavailable"
        severity = "medium"
        uncertainty = ["unavailable exchange-flow evidence must not be treated as neutral risk context."]
    else:
        state = status
        severity = "medium" if status in {"partial", "stale", "missing_availability"} else "unknown"
        uncertainty = [f"exchange-flow source availability status is {status}."]
    return {
        "state": state,
        "severity": severity,
        "confidence": "low" if status != "succeeded" else "medium",
        "as_of": view.get("input_window_end"),
        "metrics": {
            "availability_status": view.get("status"),
            "row_count": view.get("row_count"),
        },
        "thresholds": EXCHANGE_FLOW_THRESHOLDS,
        "evidence": [
            {
                "source_artifact": ONCHAIN_FLOW_VIEWS_ARTIFACT,
                "evidence_type": "source_availability",
                "status": view.get("status"),
                "storage_ref": view.get("storage_ref"),
            }
        ],
        "uncertainty": _unique_sorted([*uncertainty, *source_state["uncertainty"]]),
        "warnings": [],
        "errors": [],
    }


def _source_state(raw: dict[str, Any], view: dict[str, Any]) -> dict[str, Any]:
    has_raw_source = bool(raw)
    availability = [
        item
        for item in _list(raw.get("availability"))
        if isinstance(item, dict)
        and item.get("source") == view.get("source")
        and item.get("data_class") == view.get("data_class")
    ]
    raw_errors = [
        item
        for item in _list(raw.get("errors"))
        if isinstance(item, dict)
        and item.get("source") == view.get("source")
        and item.get("data_class") == view.get("data_class")
    ]
    statuses = {str(item.get("status")) for item in availability if isinstance(item.get("status"), str)}
    warnings = []
    errors = []
    uncertainty = []
    for item in availability:
        status = item.get("status")
        if status in {"failed", "insufficient_data", "partial", "stale", "unavailable"}:
            reason = item.get("reason") or status
            warnings.append(
                f"on-chain flow source availability is {status} for {view.get('data_class')}: {reason}."
            )
            uncertainty.append(f"source availability is {status}.")
    for item in raw_errors:
        errors.append(
            {
                "source": item.get("source"),
                "data_class": item.get("data_class"),
                "message": item.get("message"),
                "error_type": item.get("error_type"),
            }
        )
    if "failed" in statuses:
        status = "failed"
    elif "unavailable" in statuses:
        status = "unavailable"
    elif "stale" in statuses:
        status = "stale"
    elif "insufficient_data" in statuses:
        status = "insufficient"
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


def _stablecoin_state_from_change(change_pct: float | None) -> tuple[str, str]:
    if change_pct is None:
        return "insufficient_evidence", "unknown"
    if change_pct <= STABLECOIN_THRESHOLDS["sharp_supply_contraction_change_pct"]:
        return "sharp_stablecoin_supply_contraction", "high"
    if change_pct <= STABLECOIN_THRESHOLDS["supply_contraction_change_pct"]:
        return "stablecoin_supply_contraction", "medium"
    if change_pct >= STABLECOIN_THRESHOLDS["sharp_supply_expansion_change_pct"]:
        return "sharp_stablecoin_supply_expansion", "medium"
    if change_pct >= STABLECOIN_THRESHOLDS["supply_expansion_change_pct"]:
        return "stablecoin_supply_expansion", "low"
    return "normal", "low"


def _chain_activity_state_from_change(change_pct: float | None) -> tuple[str, str]:
    if change_pct is None:
        return "insufficient_evidence", "unknown"
    if change_pct >= CHAIN_ACTIVITY_THRESHOLDS["surging_activity_change_pct"]:
        return "surging_chain_activity", "high"
    if change_pct >= CHAIN_ACTIVITY_THRESHOLDS["elevated_activity_change_pct"]:
        return "elevated_chain_activity", "medium"
    if change_pct <= CHAIN_ACTIVITY_THRESHOLDS["sharply_depressed_activity_change_pct"]:
        return "sharply_depressed_chain_activity", "high"
    if change_pct <= CHAIN_ACTIVITY_THRESHOLDS["depressed_activity_change_pct"]:
        return "depressed_chain_activity", "medium"
    return "normal", "low"


def _network_congestion_state_from_metrics(latest: float, change_pct: float | None) -> tuple[str, str]:
    if latest >= NETWORK_CONGESTION_THRESHOLDS["severe_mempool_size_bytes"] or (
        change_pct is not None and change_pct >= NETWORK_CONGESTION_THRESHOLDS["severe_mempool_change_pct"]
    ):
        return "severe_network_congestion", "high"
    if latest >= NETWORK_CONGESTION_THRESHOLDS["elevated_mempool_size_bytes"] or (
        change_pct is not None and change_pct >= NETWORK_CONGESTION_THRESHOLDS["elevated_mempool_change_pct"]
    ):
        return "elevated_network_congestion", "medium"
    return "normal", "low"


def _empty_state(
    state: str,
    *,
    thresholds: dict[str, Any],
    rows: list[dict[str, Any]],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    severity = "medium" if state in {"failed", "stale", "unavailable"} else "unknown"
    return {
        "state": state,
        "severity": severity,
        "confidence": "low",
        "as_of": rows[-1].get("as_of") if rows else None,
        "metrics": {"observations": len(rows)},
        "thresholds": thresholds,
        "evidence": [],
        "uncertainty": [f"{state} prevents deterministic on-chain flow context."],
        "warnings": warnings or [],
        "errors": [],
    }


def _evidence(
    rows: list[dict[str, Any]],
    *,
    metric_name: str,
    latest_value: float,
    rolling_change: float | None,
    rolling_change_pct: float | None,
) -> list[dict[str, Any]]:
    latest_row = rows[-1] if rows else {}
    evidence = [
        {
            "metric": metric_name,
            "value": latest_value,
            "as_of": latest_row.get("as_of") if isinstance(latest_row, dict) else None,
            "source_artifact": ONCHAIN_FLOW_VIEWS_ARTIFACT,
        }
    ]
    if rolling_change is not None:
        evidence.append(
            {
                "metric": f"{metric_name}_rolling_change",
                "value": rolling_change,
                "value_pct": rolling_change_pct,
                "window_start": rows[0].get("as_of") if rows and isinstance(rows[0], dict) else None,
                "window_end": latest_row.get("as_of") if isinstance(latest_row, dict) else None,
                "source_artifact": ONCHAIN_FLOW_VIEWS_ARTIFACT,
            }
        )
    return evidence


def _metric_evidence(
    points: list[dict[str, Any]],
    *,
    metric_name: str,
    latest_value: float,
    rolling_change: float | None,
    rolling_change_pct: float | None,
) -> list[dict[str, Any]]:
    latest_point = points[-1] if points else {}
    evidence = [
        {
            "metric": metric_name,
            "value": latest_value,
            "as_of": latest_point.get("as_of"),
            "source_artifact": ONCHAIN_FLOW_VIEWS_ARTIFACT,
        }
    ]
    if rolling_change is not None:
        evidence.append(
            {
                "metric": f"{metric_name}_rolling_change",
                "value": rolling_change,
                "value_pct": rolling_change_pct,
                "window_start": points[0].get("as_of") if points else None,
                "window_end": latest_point.get("as_of"),
                "source_artifact": ONCHAIN_FLOW_VIEWS_ARTIFACT,
            }
        )
    return evidence


def _view_records(view: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for record in _list(view.get("records")):
        if isinstance(record, dict):
            records.append(record)
    return sorted(records, key=lambda record: str(record.get("as_of") or ""))


def _metric_series(rows: list[dict[str, Any]], metric_name: str) -> list[float]:
    return [point["value"] for point in _metric_points(rows, metric_name)]


def _metric_points(rows: list[dict[str, Any]], metric_name: str) -> list[dict[str, Any]]:
    values = []
    for row in rows:
        metrics = row.get("metrics")
        if not isinstance(metrics, dict):
            continue
        value = metrics.get(metric_name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.append({"as_of": row.get("as_of"), "value": float(value)})
    return sorted(values, key=lambda point: str(point.get("as_of") or ""))


def _optional_change_metrics(
    points: list[dict[str, Any]],
    *,
    first_key: str,
    latest_key: str,
    change_key: str,
    change_pct_key: str,
    observations_key: str,
) -> dict[str, Any]:
    if not points:
        return {}
    first = points[0]["value"]
    latest = points[-1]["value"]
    change = latest - first if len(points) >= 2 else None
    change_pct = _safe_change_pct(first, latest) if len(points) >= 2 else None
    return {
        first_key: first,
        latest_key: latest,
        change_key: change,
        change_pct_key: change_pct,
        observations_key: len(points),
    }


def _latest_units(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    units = rows[-1].get("units")
    return dict(units) if isinstance(units, dict) else {}


def _safe_change_pct(first: float, latest: float) -> float | None:
    if first == 0:
        return None
    return (latest - first) / abs(first)


def _confidence(status: str, base: str) -> str:
    if status == "succeeded":
        return base
    if status == "bounded" and base == "medium":
        return "medium"
    return "low"


def _context_id(*, context_type: str, source: str, asset: str, chain: str, as_of: str) -> str:
    return f"onchain_flow_context:{context_type}:{source}:{asset}:{chain}:{as_of}"


def _is_stale(value: str, *, now: str) -> bool:
    parsed = _parse_optional_utc(value)
    now_value = _parse_optional_utc(now)
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
    run.manifest["artifacts"]["onchain_flow_context"] = ONCHAIN_FLOW_CONTEXT_ARTIFACT
    run.manifest["onchain_flow_context"] = {
        "status": artifact["status"],
        "artifact": ONCHAIN_FLOW_CONTEXT_ARTIFACT,
        "records": counts["records"],
        "stablecoin_liquidity": counts["stablecoin_liquidity"],
        "chain_activity": counts["chain_activity"],
        "network_congestion": counts["network_congestion"],
        "exchange_flow_source_availability": counts["exchange_flow_source_availability"],
        "warnings": counts["warnings"],
        "errors": counts["errors"],
        "states": counts["states"],
        "severities": counts["severities"],
        "statuses": counts["statuses"],
    }
    manifest_counts = run.manifest.setdefault("counts", {})
    manifest_counts["onchain_flow_context_records"] = counts["records"]
    manifest_counts["onchain_flow_context_stablecoin_liquidity"] = counts["stablecoin_liquidity"]
    manifest_counts["onchain_flow_context_chain_activity"] = counts["chain_activity"]
    manifest_counts["onchain_flow_context_network_congestion"] = counts["network_congestion"]
    manifest_counts["onchain_flow_context_exchange_flow_source_availability"] = counts[
        "exchange_flow_source_availability"
    ]
    manifest_counts["onchain_flow_context_warnings"] = counts["warnings"]
    manifest_counts["onchain_flow_context_errors"] = counts["errors"]


def _record_zero_counts(run: RunContext) -> None:
    counts = run.manifest.setdefault("counts", {})
    counts["onchain_flow_context_records"] = 0
    counts["onchain_flow_context_stablecoin_liquidity"] = 0
    counts["onchain_flow_context_chain_activity"] = 0
    counts["onchain_flow_context_network_congestion"] = 0
    counts["onchain_flow_context_exchange_flow_source_availability"] = 0
    counts["onchain_flow_context_warnings"] = 0
    counts["onchain_flow_context_errors"] = 0


def _counts(
    records: list[dict[str, Any]],
    *,
    warnings: list[str],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "records": len(records),
        "stablecoin_liquidity": sum(1 for record in records if record.get("context_type") == "stablecoin_liquidity"),
        "chain_activity": sum(1 for record in records if record.get("context_type") == "chain_activity"),
        "network_congestion": sum(1 for record in records if record.get("context_type") == "network_congestion"),
        "exchange_flow_source_availability": sum(
            1 for record in records if record.get("context_type") == "exchange_flow_source_availability"
        ),
        "succeeded": sum(1 for record in records if record.get("status") == "succeeded"),
        "bounded": sum(1 for record in records if record.get("status") == "bounded"),
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


def _artifact_status(
    records: list[dict[str, Any]],
    *,
    warnings: list[str],
    errors: list[dict[str, Any]],
) -> str:
    if errors and not records:
        return "failed"
    if not records:
        return "warning" if warnings or errors else "skipped"
    statuses = {str(record.get("status")) for record in records}
    if statuses == {"succeeded"} and not warnings and not errors:
        return "ok"
    return "warning"


def _value_counts(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = record.get(field)
        if isinstance(value, str) and value:
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _record_sort_key(record: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(record.get("context_type") or ""),
        str(record.get("source") or ""),
        str(record.get("asset") or ""),
        str(record.get("chain") or ""),
        str(record.get("as_of") or ""),
    )


def _onchain_flow_config(config: dict[str, Any]) -> dict[str, Any]:
    onchain_flow = config.get("onchain_flow")
    return onchain_flow if isinstance(onchain_flow, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value or [] if isinstance(item, str) and item.strip()]


def _error_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _unique_sorted(values: list[str]) -> list[str]:
    return sorted(set(values))


def _parse_optional_utc(value: str) -> datetime | None:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        return None
    return timestamp.astimezone(timezone.utc).replace(microsecond=0)


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("created_at must include a UTC offset.")
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        parsed = _parse_optional_utc(value)
        if parsed is None:
            raise ValueError("created_at must be an ISO 8601 UTC string.")
        timestamp = parsed
    else:
        raise ValueError("created_at must be a datetime or ISO 8601 UTC string.")
    return timestamp.isoformat().replace("+00:00", "Z")
