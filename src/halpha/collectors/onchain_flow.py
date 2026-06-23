from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener, urlopen

from halpha.data.public_capabilities import (
    ONCHAIN_FLOW_EXCHANGE_FLOW_UNAVAILABLE_REASON,
    onchain_flow_data_class_capability,
    unsupported_onchain_flow_raw_collection_reason,
)
from halpha.data.raw_artifacts import RawArtifactError, validate_onchain_flow_raw_artifact
from halpha.runtime.pipeline_contracts import RunContext
from halpha.runtime.public_http import market_proxy_url_from_config, urlopen_from_public_proxy
from halpha.storage import write_json


STAGE_NAME = "collect_onchain_flow_data"
ONCHAIN_FLOW_ARTIFACT = "raw/onchain_flow.json"
PUBLIC_AGGREGATE_SOURCE = "public_aggregate"
DEFILLAMA_STABLECOINS_SOURCE = "defillama_stablecoins"
BLOCKCHAIN_COM_CHARTS_SOURCE = "blockchain_com_charts"
DEFILLAMA_STABLECOIN_CHARTS_URL = "https://stablecoins.llama.fi/stablecoincharts/all"
BLOCKCHAIN_CHARTS_BASE_URL = "https://api.blockchain.info/charts"
CHAIN_ACTIVITY_CHART = "n-transactions"
NETWORK_CONGESTION_CHART = "mempool-size"
REQUEST_TIMEOUT_SECONDS = 20


class OnchainFlowCollectionError(Exception):
    pass


def collect_onchain_flow_data(config: dict[str, Any], run: RunContext) -> list[str]:
    onchain_flow = _onchain_flow_config(config)
    if not onchain_flow.get("enabled"):
        run.manifest["onchain_flow"] = {
            "status": "skipped",
            "reason": "onchain_flow is disabled or not configured",
        }
        _record_manifest_counts(run, items=[], availability=[], errors=[])
        return []

    raw = collect_onchain_flow_raw(
        onchain_flow,
        proxy_url=market_proxy_url_from_config(config, error_factory=OnchainFlowCollectionError),
    )
    artifact_path = run.raw_dir / "onchain_flow.json"
    write_json(artifact_path, raw)
    run.manifest["artifacts"]["raw_onchain_flow"] = ONCHAIN_FLOW_ARTIFACT
    run.manifest["onchain_flow"] = _manifest_summary(raw)
    _record_manifest_counts(run, items=raw["items"], availability=raw["availability"], errors=raw["errors"])
    return [ONCHAIN_FLOW_ARTIFACT]


def collect_onchain_flow_raw(
    onchain_flow: dict[str, Any],
    *,
    proxy_url: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_value = _utc_now() if now is None else now.astimezone(timezone.utc)
    collected_at = _utc_timestamp(now_value)
    source = str(onchain_flow.get("source") or "")
    lookback_days = _positive_int(onchain_flow.get("lookback_days"), default=7)
    window_start = now_value - timedelta(days=lookback_days)
    window_end = now_value
    raw = _raw_artifact(
        source,
        collected_at,
        window_start=_utc_timestamp(window_start),
        window_end=_utc_timestamp(window_end),
    )

    data_classes = _string_list(onchain_flow.get("data_classes"))
    if source != PUBLIC_AGGREGATE_SOURCE:
        for data_class in data_classes:
            raw["availability"].append(
                _availability_record(
                    source=source,
                    data_class=data_class,
                    status="unavailable",
                    reason=unsupported_onchain_flow_raw_collection_reason(data_class, source),
                )
            )
        validate_onchain_flow_raw_artifact(raw, ONCHAIN_FLOW_ARTIFACT)
        return raw

    if "stablecoin_supply" in data_classes:
        _collect_stablecoin_supply(raw, onchain_flow, window_start=window_start, proxy_url=proxy_url)
    if "chain_activity" in data_classes:
        _collect_blockchain_chart(
            raw,
            onchain_flow,
            data_class="chain_activity",
            chart_name=CHAIN_ACTIVITY_CHART,
            endpoint="blockchain_chart_n_transactions",
            metric_name="transaction_count",
            unit_name="transactions",
            window_start=window_start,
            proxy_url=proxy_url,
        )
    if "network_congestion" in data_classes:
        _collect_blockchain_chart(
            raw,
            onchain_flow,
            data_class="network_congestion",
            chart_name=NETWORK_CONGESTION_CHART,
            endpoint="blockchain_chart_mempool_size",
            metric_name="mempool_size_bytes",
            unit_name="bytes",
            window_start=window_start,
            proxy_url=proxy_url,
        )
    if "exchange_flow_availability" in data_classes:
        raw["availability"].append(_exchange_flow_availability_record())

    try:
        validate_onchain_flow_raw_artifact(raw, ONCHAIN_FLOW_ARTIFACT)
    except RawArtifactError as exc:
        raw["errors"].append(_collector_error(source=source, data_class="artifact", message=str(exc)))
    return raw


def _collect_stablecoin_supply(
    raw: dict[str, Any],
    onchain_flow: dict[str, Any],
    *,
    window_start: datetime,
    proxy_url: str | None,
) -> None:
    source_url = str(onchain_flow.get("stablecoin_source_url") or DEFILLAMA_STABLECOIN_CHARTS_URL)
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    parsed_count = 0
    try:
        payload = _request_json(source_url, proxy_url=proxy_url)
        if not isinstance(payload, list):
            raise OnchainFlowCollectionError("stablecoin supply response must be a JSON list.")
        parsed_count = len(payload)
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            try:
                record = _stablecoin_record(entry, source_url=source_url)
            except (TypeError, ValueError) as exc:
                errors.append(
                    _parse_error(
                        source=DEFILLAMA_STABLECOINS_SOURCE,
                        endpoint="stablecoincharts_all",
                        data_class="stablecoin_supply",
                        message=str(exc),
                        raw_fields=_bounded_raw_fields(entry),
                    )
                )
                continue
            if _parse_timestamp(record["as_of"]) >= window_start:
                records.append(record)
    except OnchainFlowCollectionError as exc:
        errors.append(
            _collector_error(
                source=DEFILLAMA_STABLECOINS_SOURCE,
                data_class="stablecoin_supply",
                message=str(exc),
                endpoint="stablecoincharts_all",
                source_url=source_url,
            )
        )

    raw["items"].extend(records)
    raw["errors"].extend(errors)
    raw["availability"].append(
        _availability_record(
            source=DEFILLAMA_STABLECOINS_SOURCE,
            data_class="stablecoin_supply",
            status=_window_status(records=records, errors=errors, parsed_count=parsed_count),
            endpoint="stablecoincharts_all",
            record_count=len(records),
            parsed_record_count=parsed_count,
            error_count=len(errors),
            source_url=source_url,
        )
    )


def _collect_blockchain_chart(
    raw: dict[str, Any],
    onchain_flow: dict[str, Any],
    *,
    data_class: str,
    chart_name: str,
    endpoint: str,
    metric_name: str,
    unit_name: str,
    window_start: datetime,
    proxy_url: str | None,
) -> None:
    if "bitcoin" not in _string_list(onchain_flow.get("chains")):
        raw["availability"].append(
            _availability_record(
                source=BLOCKCHAIN_COM_CHARTS_SOURCE,
                data_class=data_class,
                status="skipped",
                endpoint=endpoint,
                reason="bitcoin chain is not configured.",
            )
        )
        return

    source_url = _blockchain_chart_url(onchain_flow, data_class=data_class, chart_name=chart_name)
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    parsed_count = 0
    try:
        payload = _request_json(source_url, proxy_url=proxy_url)
        if not isinstance(payload, dict):
            raise OnchainFlowCollectionError(f"{data_class} response must be a JSON object.")
        values = payload.get("values")
        if not isinstance(values, list):
            raise OnchainFlowCollectionError(f"{data_class} response values must be a list.")
        parsed_count = len(values)
        chart_unit = str(payload.get("unit") or unit_name)
        chart_title = str(payload.get("name") or chart_name)
        for entry in values:
            if not isinstance(entry, dict):
                continue
            try:
                record = _blockchain_chart_record(
                    entry,
                    data_class=data_class,
                    endpoint=endpoint,
                    metric_name=metric_name,
                    unit_name=chart_unit,
                    chart_name=chart_name,
                    chart_title=chart_title,
                    source_url=source_url,
                )
            except (TypeError, ValueError) as exc:
                errors.append(
                    _parse_error(
                        source=BLOCKCHAIN_COM_CHARTS_SOURCE,
                        endpoint=endpoint,
                        data_class=data_class,
                        message=str(exc),
                        raw_fields=_bounded_raw_fields(entry),
                    )
                )
                continue
            if _parse_timestamp(record["as_of"]) >= window_start:
                records.append(record)
    except OnchainFlowCollectionError as exc:
        errors.append(
            _collector_error(
                source=BLOCKCHAIN_COM_CHARTS_SOURCE,
                data_class=data_class,
                message=str(exc),
                endpoint=endpoint,
                source_url=source_url,
            )
        )

    raw["items"].extend(records)
    raw["errors"].extend(errors)
    raw["availability"].append(
        _availability_record(
            source=BLOCKCHAIN_COM_CHARTS_SOURCE,
            data_class=data_class,
            status=_window_status(records=records, errors=errors, parsed_count=parsed_count),
            endpoint=endpoint,
            record_count=len(records),
            parsed_record_count=parsed_count,
            error_count=len(errors),
            source_url=source_url,
        )
    )


def _request_json(source_url: str, *, proxy_url: str | None) -> Any:
    request = Request(source_url, headers={"User-Agent": "Halpha/0.0.0"})
    urlopen_func = urlopen_from_public_proxy(
        proxy_url,
        error_factory=OnchainFlowCollectionError,
        default_urlopen=urlopen,
        proxy_handler_factory=ProxyHandler,
        opener_factory=build_opener,
    )
    try:
        with urlopen_func(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read()
    except HTTPError as exc:
        detail = _read_error_detail(exc)
        raise OnchainFlowCollectionError(f"on-chain flow request failed: HTTP {exc.code}{detail}") from exc
    except URLError as exc:
        raise OnchainFlowCollectionError(f"on-chain flow request failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise OnchainFlowCollectionError("on-chain flow request timed out") from exc

    try:
        return json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise OnchainFlowCollectionError(f"on-chain flow response is not valid JSON: {exc.msg}") from exc


def _stablecoin_record(entry: dict[str, Any], *, source_url: str) -> dict[str, Any]:
    as_of = _timestamp_from_epoch_seconds(entry.get("date"))
    circulating = _nested_pegged_usd(entry.get("totalCirculating"))
    circulating_usd = _nested_pegged_usd(entry.get("totalCirculatingUSD"))
    if circulating_usd is None and circulating is None:
        raise ValueError("stablecoin supply record has no usable peggedUSD metric.")
    metrics: dict[str, float] = {}
    units: dict[str, str] = {}
    if circulating is not None:
        metrics["total_circulating"] = circulating
        units["total_circulating"] = "token_units"
    if circulating_usd is not None:
        metrics["total_circulating_usd"] = circulating_usd
        units["total_circulating_usd"] = "USD"
    return {
        "item_id": f"onchain_flow:stablecoin_supply:{DEFILLAMA_STABLECOINS_SOURCE}:all:{as_of}",
        "data_class": "stablecoin_supply",
        "source": DEFILLAMA_STABLECOINS_SOURCE,
        "asset": "ALL_STABLECOINS",
        "chain": "all",
        "as_of": as_of,
        "endpoint": "stablecoincharts_all",
        "metrics": metrics,
        "units": units,
        "raw_fields": {
            "source_url": source_url,
            "date": entry.get("date"),
        },
        "warnings": [],
        "errors": [],
    }


def _blockchain_chart_record(
    entry: dict[str, Any],
    *,
    data_class: str,
    endpoint: str,
    metric_name: str,
    unit_name: str,
    chart_name: str,
    chart_title: str,
    source_url: str,
) -> dict[str, Any]:
    as_of = _timestamp_from_epoch_seconds(entry.get("x"))
    metric_value = _finite_number(entry.get("y"), f"{data_class} y")
    return {
        "item_id": f"onchain_flow:{data_class}:{BLOCKCHAIN_COM_CHARTS_SOURCE}:bitcoin:{as_of}",
        "data_class": data_class,
        "source": BLOCKCHAIN_COM_CHARTS_SOURCE,
        "asset": "BTC",
        "chain": "bitcoin",
        "as_of": as_of,
        "endpoint": endpoint,
        "metrics": {
            metric_name: metric_value,
        },
        "units": {
            metric_name: unit_name,
        },
        "raw_fields": {
            "source_url": source_url,
            "chart_name": chart_name,
            "chart_title": chart_title,
            "x": entry.get("x"),
            "y": entry.get("y"),
        },
        "warnings": [],
        "errors": [],
    }


def _blockchain_chart_url(onchain_flow: dict[str, Any], *, data_class: str, chart_name: str) -> str:
    configured_key = {
        "chain_activity": "chain_activity_source_url",
        "network_congestion": "network_congestion_source_url",
    }[data_class]
    configured = onchain_flow.get(configured_key)
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    lookback_days = _positive_int(onchain_flow.get("lookback_days"), default=7)
    query = urlencode({"timespan": f"{lookback_days}days", "format": "json", "sampled": "false"})
    return f"{BLOCKCHAIN_CHARTS_BASE_URL}/{chart_name}?{query}"


def _raw_artifact(source_name: str, collected_at: str, *, window_start: str, window_end: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "onchain_flow_raw",
        "collector": "onchain_flow",
        "collection_method": "public_http",
        "source": {
            "name": source_name,
            "url": "https://stablecoins.llama.fi;https://api.blockchain.info",
        },
        "collected_at": collected_at,
        "window": {
            "lookback_start": window_start,
            "lookback_end": window_end,
        },
        "items": [],
        "availability": [],
        "warnings": [],
        "errors": [],
    }


def _availability_record(
    *,
    source: str,
    data_class: str,
    status: str,
    endpoint: str | None = None,
    record_count: int = 0,
    parsed_record_count: int = 0,
    error_count: int = 0,
    reason: str | None = None,
    source_url: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "source": source,
        "data_class": data_class,
        "status": status,
        "record_count": record_count,
        "parsed_record_count": parsed_record_count,
        "error_count": error_count,
    }
    if endpoint is not None:
        record["endpoint"] = endpoint
    if reason is not None:
        record["reason"] = reason
    if source_url is not None:
        record["source_url"] = source_url
    return record


def _exchange_flow_availability_record() -> dict[str, Any]:
    capability = onchain_flow_data_class_capability("exchange_flow_availability")
    record = _availability_record(
        source=PUBLIC_AGGREGATE_SOURCE,
        data_class="exchange_flow_availability",
        status="unavailable",
        endpoint="exchange_flow_periodic_public_source",
        reason=capability.unavailable_reason if capability else ONCHAIN_FLOW_EXCHANGE_FLOW_UNAVAILABLE_REASON,
    )
    record.update(
        {
            "limitations": list(capability.limitations) if capability else [],
            "downstream_implication": capability.downstream_implication if capability else None,
        }
    )
    return record


def _window_status(*, records: list[dict[str, Any]], errors: list[dict[str, Any]], parsed_count: int) -> str:
    if records and errors:
        return "partial"
    if records:
        return "succeeded"
    if errors and parsed_count == 0:
        return "failed"
    if errors:
        return "partial"
    if parsed_count == 0:
        return "insufficient_data"
    return "stale"


def _manifest_summary(raw: dict[str, Any]) -> dict[str, Any]:
    statuses = sorted(
        {
            str(item.get("status"))
            for item in raw.get("availability", [])
            if isinstance(item, dict) and item.get("status")
        }
    )
    return {
        "status": _artifact_status(raw),
        "artifact": ONCHAIN_FLOW_ARTIFACT,
        "item_count": len(raw.get("items", [])),
        "availability_count": len(raw.get("availability", [])),
        "error_count": len(raw.get("errors", [])),
        "availability_statuses": statuses,
    }


def _artifact_status(raw: dict[str, Any]) -> str:
    statuses = {
        str(item.get("status"))
        for item in raw.get("availability", [])
        if isinstance(item, dict) and item.get("status")
    }
    if raw.get("errors") and not raw.get("items"):
        return "failed"
    if "partial" in statuses:
        return "partial"
    if "failed" in statuses:
        return "failed"
    if "stale" in statuses:
        return "stale"
    if "insufficient_data" in statuses:
        return "insufficient_data"
    if "unavailable" in statuses and not raw.get("items"):
        return "unavailable"
    if raw.get("items"):
        return "succeeded"
    return "warning"


def _record_manifest_counts(
    run: RunContext,
    *,
    items: list[dict[str, Any]],
    availability: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    counts = run.manifest.setdefault("counts", {})
    counts["onchain_flow_items"] = len(items)
    counts["onchain_flow_errors"] = len(errors)
    counts["onchain_flow_availability"] = len(availability)
    counts["onchain_flow_unavailable"] = sum(1 for item in availability if item.get("status") == "unavailable")
    counts["onchain_flow_partial"] = sum(1 for item in availability if item.get("status") == "partial")
    counts["onchain_flow_stale"] = sum(1 for item in availability if item.get("status") == "stale")


def _collector_error(
    *,
    source: str,
    data_class: str,
    message: str,
    endpoint: str | None = None,
    source_url: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "source": source,
        "data_class": data_class,
        "error_type": "collector_error",
        "message": message,
    }
    if endpoint is not None:
        record["endpoint"] = endpoint
    if source_url is not None:
        record["source_url"] = source_url
    return record


def _parse_error(
    *,
    source: str,
    endpoint: str,
    data_class: str,
    message: str,
    raw_fields: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source": source,
        "endpoint": endpoint,
        "data_class": data_class,
        "error_type": "parse_error",
        "message": message,
        "raw_fields": raw_fields,
    }


def _onchain_flow_config(config: dict[str, Any]) -> dict[str, Any]:
    onchain_flow = config.get("onchain_flow")
    return onchain_flow if isinstance(onchain_flow, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _positive_int(value: Any, *, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return default


def _nested_pegged_usd(value: Any) -> float | None:
    if not isinstance(value, dict):
        return None
    return _optional_finite_number(value.get("peggedUSD"))


def _optional_finite_number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if number == number and number not in {float("inf"), float("-inf")}:
            return number
    return None


def _finite_number(value: Any, field: str) -> float:
    number = _optional_finite_number(value)
    if number is None:
        raise ValueError(f"{field} must be a finite number.")
    return number


def _timestamp_from_epoch_seconds(value: Any) -> str:
    if isinstance(value, str) and value.strip().isdigit():
        seconds = int(value.strip())
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = int(value)
    else:
        raise ValueError("timestamp must be epoch seconds.")
    return _utc_timestamp(datetime.fromtimestamp(seconds, tz=timezone.utc))


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _bounded_raw_fields(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): value[key] for key in list(value)[:10]}
    return {"value": str(value)[:200]}


def _read_error_detail(error: HTTPError) -> str:
    try:
        body = error.read().decode("utf-8").strip()
    except Exception:
        body = ""
    if not body:
        return ""
    excerpt = body[:200].replace("\n", " ")
    return f": {excerpt}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_timestamp(value: datetime | None = None) -> str:
    timestamp = value or _utc_now()
    timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    return timestamp.isoformat().replace("+00:00", "Z")
