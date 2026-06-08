from __future__ import annotations

import json
from datetime import datetime, timezone
from json import JSONDecodeError
from typing import Any

from .pipeline import PipelineError, RunContext
from .storage import write_json


BUILD_MARKET_SIGNALS_STAGE = "build_market_signals"
BUILD_MARKET_SIGNAL_MATERIAL_STAGE = "build_market_signal_material"
MARKET_STRATEGY_SIGNALS_ARTIFACT = "analysis/market_strategy_signals.json"
QUANT_STRATEGY_RUNS_ARTIFACT = "analysis/quant_strategy_runs.json"
MARKET_SIGNALS_ARTIFACT = "analysis/market_signals.json"
MARKET_SIGNAL_MATERIAL_ARTIFACT = "analysis/market_signal_material.md"
MARKET_DATA_VIEWS_ARTIFACT = "raw/market_data_views.json"
MARKET_SIGNALS_SCHEMA_VERSION = 1
MARKET_SIGNAL_MATERIAL_SCHEMA_VERSION = 1


def build_market_signals(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    if not _quant_enabled(config):
        run.manifest["counts"]["market_signals"] = 0
        run.manifest["counts"]["market_signals_insufficient_data"] = 0
        return []

    strategy_artifact = _read_json_artifact(
        run.analysis_dir / "market_strategy_signals.json",
        MARKET_STRATEGY_SIGNALS_ARTIFACT,
        producer_stage="evaluate_market_strategy_signals",
        stage=BUILD_MARKET_SIGNALS_STAGE,
    )
    strategy_signals = _signals_from_artifact(strategy_artifact, stage=BUILD_MARKET_SIGNALS_STAGE)
    created_at = _created_at(strategy_artifact, now)
    signals = [_normalize_signal(signal, created_at=created_at) for signal in strategy_signals]

    artifact = {
        "schema_version": MARKET_SIGNALS_SCHEMA_VERSION,
        "artifact_type": "market_signals",
        "created_at": created_at,
        "source_artifacts": _market_signal_source_artifacts(strategy_artifact),
        "signals": signals,
    }
    write_json(run.analysis_dir / "market_signals.json", artifact)
    run.manifest["artifacts"]["market_signals"] = MARKET_SIGNALS_ARTIFACT
    run.manifest["counts"]["market_signals"] = len(signals)
    run.manifest["counts"]["market_signals_insufficient_data"] = sum(
        1 for signal in signals if signal["insufficient_data"]
    )
    return [MARKET_SIGNALS_ARTIFACT]


def build_market_signal_material(config: dict[str, Any], run: RunContext) -> list[str]:
    if not _quant_enabled(config):
        run.manifest["counts"]["market_signal_material_records"] = 0
        return []

    market_signals = _read_json_artifact(
        run.analysis_dir / "market_signals.json",
        MARKET_SIGNALS_ARTIFACT,
        producer_stage=BUILD_MARKET_SIGNALS_STAGE,
        stage=BUILD_MARKET_SIGNAL_MATERIAL_STAGE,
    )
    _signals_from_artifact(market_signals, stage=BUILD_MARKET_SIGNAL_MATERIAL_STAGE)
    output_path = run.analysis_dir / "market_signal_material.md"
    output_path.write_text(render_market_signal_material(market_signals), encoding="utf-8")
    run.manifest["artifacts"]["market_signal_material"] = MARKET_SIGNAL_MATERIAL_ARTIFACT
    run.manifest["counts"]["market_signal_material_records"] = len(market_signals["signals"])
    return [MARKET_SIGNAL_MATERIAL_ARTIFACT]


def render_market_signal_material(market_signals: dict[str, Any]) -> str:
    source_artifacts = _unique_ordered(
        [
            MARKET_SIGNALS_ARTIFACT,
            MARKET_DATA_VIEWS_ARTIFACT,
            *_string_list(market_signals.get("source_artifacts")),
        ]
    )
    lines = [
        "---",
        "artifact_type: analysis_market_signal_material",
        f"schema_version: {MARKET_SIGNAL_MATERIAL_SCHEMA_VERSION}",
        "audience: ai",
        "source_artifacts:",
        *_yaml_list(source_artifacts),
        "---",
        "",
        "# market_signal_material",
        "",
        "## source_policy",
        "",
        "```yaml",
        _yaml_block(_source_policy()).rstrip(),
        "```",
        "",
    ]

    for signal in market_signals["signals"]:
        lines.extend(
            [
                f"## record: {signal['signal_id']}",
                "",
                "```yaml",
                _yaml_block(_material_record(signal)).rstrip(),
                "```",
                "",
            ]
        )

    return "\n".join(lines)


def _normalize_signal(signal: dict[str, Any], *, created_at: str) -> dict[str, Any]:
    strategy_name = signal.get("strategy_name")
    source = signal.get("source")
    symbol = signal.get("symbol")
    timeframe = signal.get("timeframe")
    latest = signal.get("latest_candle_time") or "missing"
    return {
        "signal_id": f"market_signal:{strategy_name}:{source}:{symbol}:{timeframe}:{latest}",
        "strategy_name": strategy_name,
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "input_window_start": signal.get("input_window_start"),
        "input_window_end": signal.get("input_window_end"),
        "latest_candle_time": signal.get("latest_candle_time"),
        "direction": signal.get("direction", "unknown"),
        "strength": signal.get("strength", "unknown"),
        "confidence": signal.get("confidence", "unknown"),
        "key_values": signal.get("key_values") if isinstance(signal.get("key_values"), dict) else {},
        "evidence": _string_list(signal.get("evidence")),
        "uncertainty": _string_list(signal.get("uncertainty")),
        "insufficient_data": bool(signal.get("insufficient_data")),
        "source_artifacts": _unique_ordered(
            [MARKET_STRATEGY_SIGNALS_ARTIFACT, *_string_list(signal.get("source_artifacts"))]
        ),
        "created_at": signal.get("created_at") or created_at,
    }


def _market_signal_source_artifacts(strategy_artifact: dict[str, Any]) -> list[str]:
    source_artifacts = [MARKET_STRATEGY_SIGNALS_ARTIFACT]
    upstream = _string_list(strategy_artifact.get("source_artifacts"))
    if QUANT_STRATEGY_RUNS_ARTIFACT in upstream:
        source_artifacts.append(QUANT_STRATEGY_RUNS_ARTIFACT)
    return source_artifacts


def _material_record(signal: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_type": "market_signal",
        "signal_id": signal["signal_id"],
        "strategy_name": signal["strategy_name"],
        "source": signal["source"],
        "symbol": signal["symbol"],
        "timeframe": signal["timeframe"],
        "input_window_start": signal["input_window_start"],
        "input_window_end": signal["input_window_end"],
        "latest_candle_time": signal["latest_candle_time"],
        "direction": signal["direction"],
        "strength": signal["strength"],
        "confidence": signal["confidence"],
        "key_values": signal["key_values"],
        "evidence": signal["evidence"],
        "uncertainty": signal["uncertainty"],
        "insufficient_data": signal["insufficient_data"],
        "source_artifacts": signal["source_artifacts"],
    }


def _read_json_artifact(path, artifact: str, *, producer_stage: str, stage: str) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{artifact} was not found; {producer_stage} must run first.",
            stage=stage,
            exit_code=3,
        ) from exc
    except JSONDecodeError as exc:
        raise PipelineError(
            f"{artifact} is not valid JSON: {exc.msg}.",
            stage=stage,
            exit_code=3,
        ) from exc
    if not isinstance(loaded, dict):
        raise PipelineError(
            f"{artifact} must be a JSON object.",
            stage=stage,
            exit_code=3,
        )
    return loaded


def _signals_from_artifact(artifact: dict[str, Any], *, stage: str) -> list[dict[str, Any]]:
    signals = artifact.get("signals")
    if not isinstance(signals, list):
        raise PipelineError(
            "market signal artifacts must contain a signals list.",
            stage=stage,
            exit_code=3,
        )
    for index, signal in enumerate(signals):
        if not isinstance(signal, dict):
            raise PipelineError(
                f"signals[{index}] must be a mapping.",
                stage=stage,
                exit_code=3,
            )
    return signals


def _created_at(strategy_artifact: dict[str, Any], now: datetime | str | None) -> str:
    if now is not None:
        return _format_utc(now)
    created_at = strategy_artifact.get("created_at")
    if isinstance(created_at, str) and created_at.strip():
        return _format_utc(created_at)
    return _format_utc(None)


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise PipelineError("created_at must include a UTC offset.", exit_code=3)
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PipelineError("created_at must be an ISO 8601 UTC string.", exit_code=3) from exc
        if timestamp.tzinfo is None:
            raise PipelineError("created_at must include a UTC offset.", exit_code=3)
        timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    else:
        raise PipelineError("created_at must be a datetime or ISO 8601 UTC string.", exit_code=3)
    return timestamp.isoformat().replace("+00:00", "Z")


def _source_policy() -> dict[str, Any]:
    return {
        "signal_material_is_financial_advice": False,
        "trading_instructions_allowed": False,
        "raw_ohlcv_history_embedded": False,
        "fabricate_missing_signals": False,
        "allowed_basis": [
            "normalized_market_signals",
            "bounded_input_window_metadata",
            "key_values",
            "evidence",
            "uncertainty",
        ],
    }


def _quant_enabled(config: dict[str, Any]) -> bool:
    quant = config.get("quant")
    return isinstance(quant, dict) and quant.get("enabled") is True


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _unique_ordered(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _yaml_list(values: list[str]) -> list[str]:
    if not values:
        return ["  []"]
    return [f"  - {value}" for value in values]


def _yaml_block(data: dict[str, Any]) -> str:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise PipelineError(
            "PyYAML is required to write YAML market signal material records.",
            stage=BUILD_MARKET_SIGNAL_MATERIAL_STAGE,
            exit_code=1,
        ) from exc

    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
