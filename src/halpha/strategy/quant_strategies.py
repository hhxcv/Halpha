from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from halpha.market.market_data_views import MARKET_DATA_VIEWS_ARTIFACT, load_market_data_view_records
from halpha.runtime.pipeline_contracts import PipelineError, RunContext
from halpha.quant.parameter_diagnostics import bounded_parameter_diagnostic, parameter_diagnostic_config
from halpha.quant.registry import get_strategy_definition
from halpha.quant.strategy_records import failed_strategy_run
from halpha.quant.vectorbt_engine import engine_metadata
from halpha.storage import write_json


STAGE_NAME = "evaluate_quant_strategies"
QUANT_STRATEGY_RUNS_ARTIFACT = "analysis/quant_strategy_runs.json"
SCHEMA_VERSION = 1


def evaluate_quant_strategies(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    quant = config.get("quant")
    if not _strategy_config_enabled(quant):
        _record_zero_counts(run)
        return []

    views_artifact = _read_market_data_views(run)
    storage_dir = _storage_dir(config, run.config_path)
    created_at = _format_utc(now)
    enabled, disabled = _configured_strategies(quant)
    engine = engine_metadata()
    parameter_config = parameter_diagnostic_config(quant)
    runs = []

    for view in views_artifact.get("views", []):
        rows = load_market_data_view_records(view, storage_dir=storage_dir)
        for strategy in enabled:
            runs.append(
                _run_strategy(
                    strategy,
                    view,
                    rows,
                    engine=engine,
                    created_at=created_at,
                    parameter_config=parameter_config,
                )
            )

    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "quant_strategy_runs",
        "created_at": created_at,
        "engine": {
            **engine,
            "objects_exposed": False,
        },
        "source_artifacts": [MARKET_DATA_VIEWS_ARTIFACT],
        "runs": runs,
    }
    write_json(run.analysis_dir / "quant_strategy_runs.json", artifact)
    run.manifest["artifacts"]["quant_strategy_runs"] = QUANT_STRATEGY_RUNS_ARTIFACT
    _record_manifest_counts(run, runs, enabled=enabled, disabled=disabled)
    _record_manifest_summary(
        run,
        engine=engine,
        enabled=enabled,
        disabled=disabled,
        parameter_config=parameter_config,
        runs=runs,
    )
    return [QUANT_STRATEGY_RUNS_ARTIFACT]


def _strategy_config_enabled(quant: Any) -> bool:
    return isinstance(quant, dict) and quant.get("enabled") is True and isinstance(quant.get("strategies"), list)


def _configured_strategies(quant: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    enabled = []
    disabled = []
    for strategy in quant.get("strategies", []):
        name = str(strategy["name"])
        if strategy.get("enabled", True) is False:
            disabled.append(name)
            continue
        enabled.append(strategy)
    return enabled, disabled


def _run_strategy(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    engine: dict[str, str],
    created_at: str,
    parameter_config: dict[str, Any],
) -> dict[str, Any]:
    name = str(strategy["name"])
    definition = get_strategy_definition(name)
    if definition is None:
        return _failed_run(
            strategy,
            view,
            engine=engine,
            created_at=created_at,
            params={},
            error_type="UnsupportedStrategy",
            message=f"{name} is not implemented.",
        )
    try:
        strategy_run = definition.run(strategy, view, rows, engine=engine, created_at=created_at)
        strategy_run["parameter_diagnostic"] = bounded_parameter_diagnostic(
            strategy,
            view,
            rows,
            base_run=strategy_run,
            definition=definition,
            config=parameter_config,
            engine=engine,
            created_at=created_at,
        )
        return strategy_run
    except Exception as exc:
        return _failed_run(
            strategy,
            view,
            engine=engine,
            created_at=created_at,
            params=definition.failed_params(strategy),
            error_type=type(exc).__name__,
            message=str(exc),
        )


def _failed_run(
    strategy: dict[str, Any],
    view: dict[str, Any],
    *,
    engine: dict[str, str],
    created_at: str,
    params: dict[str, Any],
    error_type: str,
    message: str,
) -> dict[str, Any]:
    return failed_strategy_run(
        strategy,
        view,
        engine=engine,
        created_at=created_at,
        params=params,
        error_type=error_type,
        message=message,
        stage=STAGE_NAME,
    )


def _read_market_data_views(run: RunContext) -> dict[str, Any]:
    path = run.raw_dir / "market_data_views.json"
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{MARKET_DATA_VIEWS_ARTIFACT} was not found; build_market_data_views must run first.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(
            f"{MARKET_DATA_VIEWS_ARTIFACT} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(artifact, dict) or not isinstance(artifact.get("views"), list):
        raise PipelineError(
            f"{MARKET_DATA_VIEWS_ARTIFACT} must contain a views list.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    return artifact


def _storage_dir(config: dict[str, Any], config_path: Path) -> Path:
    ohlcv = config.get("market", {}).get("ohlcv", {})
    storage_dir = Path(str(ohlcv["storage_dir"]))
    if storage_dir.is_absolute():
        return storage_dir
    return config_path.parent / storage_dir


def _record_zero_counts(run: RunContext) -> None:
    run.manifest["counts"]["quant_strategy_runs"] = 0
    run.manifest["counts"]["quant_strategy_runs_succeeded"] = 0
    run.manifest["counts"]["quant_strategy_runs_failed"] = 0
    run.manifest["counts"]["quant_strategy_runs_insufficient_data"] = 0
    run.manifest["counts"]["quant_strategy_runs_skipped"] = 0
    run.manifest["counts"]["quant_strategy_runs_disabled"] = 0
    run.manifest["counts"]["quant_strategies_enabled"] = 0
    run.manifest["counts"]["quant_strategies_disabled"] = 0


def _record_manifest_counts(
    run: RunContext,
    runs: list[dict[str, Any]],
    *,
    enabled: list[dict[str, Any]],
    disabled: list[str],
) -> None:
    run.manifest["counts"]["quant_strategy_runs"] = len(runs)
    for status in ("succeeded", "failed", "insufficient_data", "skipped", "disabled"):
        run.manifest["counts"][f"quant_strategy_runs_{status}"] = sum(
            1 for item in runs if item.get("status") == status
        )
    run.manifest["counts"]["quant_strategies_enabled"] = len(enabled)
    run.manifest["counts"]["quant_strategies_disabled"] = len(disabled)


def _record_manifest_summary(
    run: RunContext,
    *,
    engine: dict[str, str],
    enabled: list[dict[str, Any]],
    disabled: list[str],
    parameter_config: dict[str, Any],
    runs: list[dict[str, Any]],
) -> None:
    run.manifest["quant_strategies"] = {
        "engine": engine,
        "enabled": [str(strategy["name"]) for strategy in enabled],
        "disabled": disabled,
        "backtest_diagnostics_enabled": any(
            isinstance(strategy.get("backtest"), dict) and strategy["backtest"].get("enabled") is True
            for strategy in enabled
        ),
        "parameter_diagnostics_enabled": parameter_config.get("enabled") is True,
        "failures": [_failure_summary(item) for item in runs if item.get("status") == "failed"],
        "insufficient_data": [
            {
                "strategy_name": item.get("strategy_name"),
                "source": item.get("source"),
                "symbol": item.get("symbol"),
                "timeframe": item.get("timeframe"),
                "input_view_id": item.get("input_view_id"),
                "row_count": item.get("data_quality", {}).get("row_count"),
                "minimum_required_rows": item.get("data_quality", {}).get("minimum_required_rows"),
            }
            for item in runs
            if item.get("status") == "insufficient_data"
        ],
    }


def _failure_summary(item: dict[str, Any]) -> dict[str, Any]:
    error = item.get("error") if isinstance(item.get("error"), dict) else {}
    return {
        "strategy_name": item.get("strategy_name"),
        "source": item.get("source"),
        "symbol": item.get("symbol"),
        "timeframe": item.get("timeframe"),
        "input_view_id": item.get("input_view_id"),
        "error_type": error.get("error_type"),
        "message": error.get("message"),
    }


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise PipelineError("created_at must include a UTC offset.", stage=STAGE_NAME, exit_code=3)
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PipelineError("created_at must be an ISO 8601 UTC string.", stage=STAGE_NAME, exit_code=3) from exc
        if timestamp.tzinfo is None:
            raise PipelineError("created_at must include a UTC offset.", stage=STAGE_NAME, exit_code=3)
        timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    else:
        raise PipelineError("created_at must be a datetime, string, or None.", stage=STAGE_NAME, exit_code=3)
    return timestamp.isoformat().replace("+00:00", "Z")
