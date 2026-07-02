from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from halpha.market.derivatives_source import (
    BINANCE_USDM_BASE_URL,
    DerivativesSourceError,
    PublicDerivativesSource,
    derivatives_request_metadata,
)
from halpha.runtime.pipeline_contracts import RunContext
from halpha.data.public_capabilities import (
    DERIVATIVES_LIQUIDATION_SUMMARY_PERIOD,
    DERIVATIVES_RAW_DATA_CLASSES,
    derivatives_data_class_capability,
    unsupported_derivatives_raw_collection_reason,
)
from halpha.data.raw_artifacts import RawArtifactError, validate_derivatives_market_raw_artifact
from halpha.storage import write_json


STAGE_NAME = "collect_derivatives_market_data"
DERIVATIVES_MARKET_ARTIFACT = "raw/derivatives_market.json"
SPREAD_DEPTH_LIMIT = 20
FUNDING_INTERVAL_HOURS = 8
FUNDING_DEFAULT_LIMIT_WITHOUT_WINDOW = 200
BINANCE_BASIS_MAX_LIMIT = 500
BASIS_PUBLIC_HISTORY_DAYS = 30
BASIS_PERIOD_MINUTES = {
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "4h": 240,
    "6h": 360,
    "12h": 720,
    "1d": 1440,
}
RATE_LIMIT_SKIP_REASON = "skipped because binance_usdm returned a derivatives rate-limit response earlier in this collection run"


def collect_derivatives_market_data(config: dict[str, Any], run: RunContext) -> list[str]:
    derivatives = _derivatives_config(config)
    if not derivatives.get("enabled"):
        _record_manifest_counts(run, items=[], availability=[], errors=[])
        return []

    collected_at = _utc_timestamp()
    raw = _raw_artifact(derivatives.get("source"), collected_at)
    symbols = _string_list(derivatives.get("symbols"))
    data_classes = _string_list(derivatives.get("data_classes"))
    periods = _string_list(derivatives.get("periods"))
    lookback = derivatives.get("lookback") if isinstance(derivatives.get("lookback"), dict) else {}

    try:
        source = PublicDerivativesSource(
            str(derivatives.get("source") or ""),
            proxy_url=_proxy_url_from_market_config(config),
            rate_limit_config_path=run.config_path,
        )
    except DerivativesSourceError as exc:
        raw["errors"].append(_collector_error(derivatives, str(exc)))
    else:
        rate_limit_state: dict[str, Any] = {}
        for data_class in data_classes:
            if data_class not in DERIVATIVES_RAW_DATA_CLASSES:
                raw["availability"].append(
                    _availability_record(
                        data_class=data_class,
                        status="unavailable",
                        reason=unsupported_derivatives_raw_collection_reason(data_class, source.source),
                    )
                )
                continue
            _collect_data_class(
                source,
                raw,
                data_class=data_class,
                symbols=symbols,
                periods=periods,
                lookback=lookback,
                rate_limit_state=rate_limit_state,
            )

    try:
        validate_derivatives_market_raw_artifact(raw, DERIVATIVES_MARKET_ARTIFACT)
    except RawArtifactError as exc:
        raw["errors"].append(_collector_error(derivatives, str(exc)))

    artifact_path = run.raw_dir / "derivatives_market.json"
    write_json(artifact_path, raw)
    run.manifest["artifacts"]["raw_derivatives_market"] = DERIVATIVES_MARKET_ARTIFACT
    _record_manifest_counts(run, items=raw["items"], availability=raw["availability"], errors=raw["errors"])
    return [DERIVATIVES_MARKET_ARTIFACT]


def _collect_data_class(
    source: PublicDerivativesSource,
    raw: dict[str, Any],
    *,
    data_class: str,
    symbols: list[str],
    periods: list[str],
    lookback: dict[str, Any],
    rate_limit_state: dict[str, Any],
) -> None:
    if data_class == "funding_rate":
        limit = _max_lookback(lookback)
        window = _funding_time_window(raw.get("collected_at"), limit=limit)
        for symbol in symbols:
            _collect_request(
                raw,
                source,
                "funding_rate_history",
                symbol=symbol,
                limit=limit,
                start_time_ms=window.get("start_time_ms"),
                end_time_ms=window.get("end_time_ms"),
                rate_limit_state=rate_limit_state,
            )
        return

    if data_class == "open_interest":
        for symbol in symbols:
            _collect_request(raw, source, "open_interest_current", symbol=symbol, rate_limit_state=rate_limit_state)
            for period in periods:
                _collect_request(
                    raw,
                    source,
                    "open_interest_history",
                    symbol=symbol,
                    period=period,
                    limit=_period_lookback(lookback, period),
                    rate_limit_state=rate_limit_state,
                )
        return

    if data_class == "premium_index":
        for symbol in symbols:
            _collect_request(raw, source, "premium_index", symbol=symbol, rate_limit_state=rate_limit_state)
        return

    if data_class == "spread_depth":
        for symbol in symbols:
            _collect_request(
                raw,
                source,
                "order_book_depth",
                symbol=symbol,
                limit=SPREAD_DEPTH_LIMIT,
                rate_limit_state=rate_limit_state,
            )
        return

    if data_class == "liquidation_summary":
        for symbol in symbols:
            raw["availability"].append(_liquidation_availability_record(symbol=symbol))
        return

    if data_class == "basis":
        for symbol in symbols:
            for period in periods:
                _collect_request(
                    raw,
                    source,
                    "basis",
                    symbol=symbol,
                    period=period,
                    limit=_basis_lookback(lookback, period),
                    rate_limit_state=rate_limit_state,
                )


def _collect_request(
    raw: dict[str, Any],
    source: PublicDerivativesSource,
    request_class: str,
    *,
    symbol: str,
    period: str | None = None,
    limit: int | None = None,
    start_time_ms: int | None = None,
    end_time_ms: int | None = None,
    rate_limit_state: dict[str, Any] | None = None,
) -> None:
    if rate_limit_state:
        _append_rate_limit_skipped_availability(
            raw,
            request_class=request_class,
            symbol=symbol,
            period=period,
            retry_after_seconds=rate_limit_state.get("retry_after_seconds"),
        )
        return

    try:
        kwargs: dict[str, Any] = {"symbol": symbol, "period": period, "limit": limit}
        if start_time_ms is not None:
            kwargs["start_time_ms"] = start_time_ms
        if end_time_ms is not None:
            kwargs["end_time_ms"] = end_time_ms
        result = source.fetch_records(request_class, **kwargs)
    except DerivativesSourceError as exc:
        raw["errors"].append(
            {
                "source": source.source,
                "market_type": "usd_m_futures",
                "request_class": request_class,
                "symbol": symbol,
                "period": period,
                "error_type": "request_config_error",
                "message": str(exc),
            }
        )
        return

    raw["items"].extend(result["records"])
    raw["errors"].extend(result["errors"])
    raw["availability"].append(
        _availability_record(
            data_class=result["data_class"],
            request_class=result["request_class"],
            endpoint=result["endpoint"],
            symbol=symbol,
            period=result["period"],
            status=_request_status(result),
            record_count=len(result["records"]),
            error_count=len(result["errors"]),
        )
    )
    rate_limit_error = _first_rate_limit_error(result["errors"])
    if rate_limit_error is not None and rate_limit_state is not None:
        rate_limit_state.update(
            {
                "source": source.source,
                "retry_after_seconds": rate_limit_error.get("retry_after_seconds"),
                "message": rate_limit_error.get("message"),
            }
        )


def _raw_artifact(source_name: Any, collected_at: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "derivatives_market_raw",
        "collector": "derivatives_market",
        "collection_method": "public_http",
        "source": {
            "name": source_name,
            "url": BINANCE_USDM_BASE_URL if source_name == "binance_usdm" else None,
        },
        "collected_at": collected_at,
        "items": [],
        "availability": [],
        "warnings": [],
        "errors": [],
    }


def _availability_record(
    *,
    data_class: str,
    status: str,
    request_class: str | None = None,
    endpoint: str | None = None,
    symbol: str | None = None,
    period: str | None = None,
    record_count: int = 0,
    error_count: int = 0,
    reason: str | None = None,
    retry_after_seconds: int | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "data_class": data_class,
        "status": status,
        "record_count": record_count,
        "error_count": error_count,
    }
    if request_class is not None:
        record["request_class"] = request_class
    if endpoint is not None:
        record["endpoint"] = endpoint
    if symbol is not None:
        record["symbol"] = symbol
    if period is not None:
        record["period"] = period
    if reason is not None:
        record["reason"] = reason
    if isinstance(retry_after_seconds, int) and retry_after_seconds > 0:
        record["retry_after_seconds"] = retry_after_seconds
    return record


def _liquidation_availability_record(*, symbol: str) -> dict[str, Any]:
    capability = derivatives_data_class_capability("liquidation_summary")
    record = _availability_record(
        data_class="liquidation_summary",
        status="unavailable",
        endpoint="liquidation_order_streams",
        symbol=symbol,
        period=capability.availability_period if capability else DERIVATIVES_LIQUIDATION_SUMMARY_PERIOD,
        reason=capability.unavailable_reason if capability else None,
    )
    record.update(
        {
            "method": "websocket_market_stream",
            "stream_name": f"{symbol.lower()}@forceOrder",
            "stream_path": "/market",
            "signed_rest_endpoint": "/fapi/v1/forceOrders",
            "signed_rest_access": "USER_DATA",
            "limitations": list(capability.limitations) if capability else [],
            "downstream_implication": capability.downstream_implication if capability else None,
        }
    )
    return record


def _request_status(result: dict[str, Any]) -> str:
    records = result.get("records") or []
    errors = result.get("errors") or []
    if records and errors:
        return "partial"
    if errors:
        return "failed"
    return "succeeded"


def _append_rate_limit_skipped_availability(
    raw: dict[str, Any],
    *,
    request_class: str,
    symbol: str,
    period: str | None,
    retry_after_seconds: Any,
) -> None:
    try:
        metadata = derivatives_request_metadata(request_class, period=period)
    except DerivativesSourceError as exc:
        raw["errors"].append(
            {
                "source": "binance_usdm",
                "market_type": "usd_m_futures",
                "request_class": request_class,
                "symbol": symbol,
                "period": period,
                "error_type": "request_config_error",
                "message": str(exc),
            }
        )
        return

    raw["availability"].append(
        _availability_record(
            data_class=metadata["data_class"],
            request_class=metadata["request_class"],
            endpoint=metadata["endpoint"],
            symbol=symbol,
            period=metadata["period"],
            status="skipped",
            reason=RATE_LIMIT_SKIP_REASON,
            retry_after_seconds=retry_after_seconds,
        )
    )


def _first_rate_limit_error(errors: Any) -> dict[str, Any] | None:
    if not isinstance(errors, list):
        return None
    for error in errors:
        if isinstance(error, dict) and error.get("error_type") == "rate_limited":
            return error
    return None


def _record_manifest_counts(
    run: RunContext,
    *,
    items: list[dict[str, Any]],
    availability: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    counts = run.manifest.setdefault("counts", {})
    counts["derivatives_market_items"] = len(items)
    counts["derivatives_market_errors"] = len(errors)
    counts["derivatives_market_availability"] = len(availability)
    counts["derivatives_market_requests"] = sum(1 for item in availability if item.get("request_class"))
    counts["derivatives_market_unavailable"] = sum(1 for item in availability if item.get("status") == "unavailable")
    counts["derivatives_market_skipped"] = sum(1 for item in availability if item.get("status") == "skipped")


def _derivatives_config(config: dict[str, Any]) -> dict[str, Any]:
    market = config.get("market")
    if not isinstance(market, dict):
        return {}
    derivatives = market.get("derivatives")
    return derivatives if isinstance(derivatives, dict) else {}


def _proxy_url_from_market_config(config: dict[str, Any]) -> str | None:
    market = config.get("market")
    if not isinstance(market, dict):
        return None
    proxy = market.get("proxy")
    if not isinstance(proxy, dict) or proxy.get("enabled") is not True:
        return None
    value = proxy.get("url")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _period_lookback(lookback: dict[str, Any], period: str) -> int | None:
    value = lookback.get(period)
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def _basis_lookback(lookback: dict[str, Any], period: str) -> int | None:
    requested = _period_lookback(lookback, period)
    if requested is None:
        return None
    capped = min(requested, BINANCE_BASIS_MAX_LIMIT)
    period_minutes = BASIS_PERIOD_MINUTES.get(period)
    if period_minutes is None:
        return capped
    public_window_records = max(1, BASIS_PUBLIC_HISTORY_DAYS * 24 * 60 // period_minutes)
    return min(capped, public_window_records)


def _max_lookback(lookback: dict[str, Any]) -> int | None:
    values = [
        value
        for value in lookback.values()
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
    ]
    return max(values) if values else None


def _funding_time_window(collected_at: Any, *, limit: int | None) -> dict[str, int]:
    if limit is None or limit <= FUNDING_DEFAULT_LIMIT_WITHOUT_WINDOW:
        return {}
    end = _parse_utc(collected_at)
    if end is None:
        return {}
    start = end - timedelta(hours=limit * FUNDING_INTERVAL_HOURS)
    return {
        "start_time_ms": _timestamp_millis(start),
        "end_time_ms": _timestamp_millis(end),
    }


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _timestamp_millis(value: datetime) -> int:
    return int(value.astimezone(timezone.utc).timestamp() * 1000)


def _collector_error(derivatives: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "source": derivatives.get("source"),
        "market_type": "usd_m_futures",
        "error_type": "collector_error",
        "message": message,
    }


def _utc_timestamp(value: datetime | None = None) -> str:
    timestamp = value or datetime.now(timezone.utc)
    timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    return timestamp.isoformat().replace("+00:00", "Z")
