from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
from typing import Any

from halpha.data.run_index import (
    RUN_INDEX_ARTIFACT,
    fetch_run_index_record,
    run_index_path,
    select_latest_run_record,
)
from halpha.market.ohlcv_quality import OHLCV_TIMEFRAME_ORDER
from halpha.market.ohlcv_source import OHLCV_SOURCE_ORDER
from halpha.quant.registry import supported_strategy_specs
from halpha.strategy.strategy_config import configured_targeted_parameter_profiles
from halpha.strategy.strategy_evaluation_history import (
    STRATEGY_EVALUATION_HISTORY_ARTIFACT,
    read_strategy_evaluation_history,
)
from halpha.storage import (
    artifact_base as _artifact_base,
    read_json_object,
    resolve_local_ref,
    safe_local_ref,
)
from halpha.utils.value_helpers import (
    as_dict as _dict,
    as_list as _list,
    stringified_list as _string_list,
)


STRATEGY_RESEARCH_NOTICE = "Strategy output is historical research material, not trading advice."
EXTERNAL_ARTIFACT_REF = "<external-artifact>"
REJECTED_EXTERNAL_REF_NAME = ".halpha_external_ref_rejected"
MAX_SUMMARY_ITEMS = 20
MAX_STANDALONE_RUNS = 50
MAX_BACKTEST_VISUALIZATION_BARS = 120
MAX_BACKTEST_VISUALIZATION_MARKERS = 1000
MAX_BACKTEST_VISUALIZATION_EQUITY_POINTS = 120
MAX_WARNING_GROUPS = 12
MAX_WARNING_GROUP_SOURCES = 5
PIPELINE_STRATEGY_ARTIFACTS = [
    ("strategy_benchmark_suite", "analysis/strategy_benchmark_suite.json"),
    ("quant_strategy_runs", "analysis/quant_strategy_runs.json"),
    ("strategy_evaluation_summary", "analysis/strategy_evaluation_summary.json"),
    ("strategy_experiment", "analysis/strategy_experiment.json"),
    ("strategy_effectiveness_gates", "analysis/strategy_effectiveness_gates.json"),
    ("strategy_lifecycle_state", "analysis/strategy_lifecycle_state.json"),
]


def dashboard_strategy_research(
    config: dict[str, Any],
    *,
    config_path: Path,
    run_id: str | None = None,
) -> dict[str, Any]:
    base = _artifact_base(config_path)
    selected_run = _selected_run(config_path, base=base, run_id=run_id)
    pipeline = _pipeline_strategy_section(selected_run, base=base)
    standalone = _standalone_strategy_section(config, config_path=config_path, base=base)
    shared_history = _shared_strategy_history_section(config_path, base=base)
    source_artifacts = sorted(
        {
            artifact
            for section in (pipeline, standalone, shared_history)
            for artifact in _string_list(section.get("source_artifacts"))
        }
    )
    warnings = [*pipeline["warnings"], *standalone["warnings"], *shared_history["warnings"]]
    errors = [*pipeline["errors"], *standalone["errors"], *shared_history["errors"]]
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_strategy_research",
        "status": _overall_status([pipeline["status"], standalone["status"], shared_history["status"]]),
        "notice": STRATEGY_RESEARCH_NOTICE,
        "selected_run": selected_run["fields"],
        "pipeline": pipeline,
        "standalone": standalone,
        "shared_history": shared_history,
        "commands": _strategy_command_options(config),
        "source_artifacts": source_artifacts,
        "warnings": warnings,
        "warning_groups": _warning_groups(warnings, source_artifacts),
        "errors": errors,
        "omitted": {
            "full_equity_curves_embedded": False,
            "full_strategy_records_embedded": False,
            "full_strategy_lifecycle_json_embedded": False,
            "vectorbt_objects_embedded": False,
            "trading_instructions_embedded": False,
        },
    }


def _strategy_command_options(config: dict[str, Any]) -> dict[str, Any]:
    specs = _configured_strategy_specs(config)
    return {
        "backtest": "available",
        "experiment": "available",
        "optimize": "available",
        "options": {
            "action_scopes": _strategy_action_scopes(),
            "evaluation_modes": ["backtest", "experiment", "optimize"],
            "market_types": _configured_market_types(specs),
            "sources": _configured_ohlcv_sources(config),
            "strategy_families": _configured_strategy_families(specs),
            "strategy_names": sorted(_configured_strategy_names(config)),
            "strategy_profiles": _configured_strategy_profiles(config, specs),
            "strategy_specs": specs,
            "symbols": _configured_symbols(config),
            "timeframes": _configured_timeframes(config),
        },
    }


def _strategy_action_scopes() -> dict[str, dict[str, Any]]:
    return {
        "backtest": {
            "window_policy": "selected_profile_range",
            "range_supported": True,
            "label": "Selected profile range",
        },
        "experiment": {
            "window_policy": "configured_benchmark_suite",
            "range_supported": False,
            "label": "Configured benchmark suite",
        },
        "optimize": {
            "window_policy": "configured_benchmark_suite",
            "range_supported": False,
            "label": "Configured benchmark suite",
        },
    }


def _configured_strategy_names(config: dict[str, Any]) -> set[str]:
    quant = config.get("quant") if isinstance(config.get("quant"), dict) else {}
    strategies = quant.get("strategies") if isinstance(quant.get("strategies"), list) else []
    return {
        str(strategy.get("name"))
        for strategy in strategies
        if isinstance(strategy, dict) and strategy.get("name") and strategy.get("enabled", True) is not False
    }


def _configured_strategy_specs(config: dict[str, Any]) -> list[dict[str, Any]]:
    configured = _configured_strategy_names(config)
    strategy_configs = _configured_strategy_map(config)
    records = []
    for spec in supported_strategy_specs():
        if spec.name in configured:
            record = spec.to_record()
            strategy_config = strategy_configs.get(spec.name, {})
            params = strategy_config.get("params") if isinstance(strategy_config.get("params"), dict) else {}
            record["configured_params"] = dict(params)
            record["targeted_params"] = configured_targeted_parameter_profiles(strategy_config)
            records.append(record)
    return records


def _configured_strategy_profiles(config: dict[str, Any], specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source = _configured_ohlcv_sources(config)[0] if _configured_ohlcv_sources(config) else "binance"
    symbols = _configured_symbols(config)
    timeframes = _configured_timeframes(config)
    fallback_symbol = symbols[0] if symbols else ""
    fallback_timeframe = timeframes[0] if timeframes else ""
    profiles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for spec in specs:
        name = str(spec.get("name") or "")
        if not name:
            continue
        base_params = _dict(spec.get("configured_params"))
        targeted = [profile for profile in _list(spec.get("targeted_params")) if isinstance(profile, dict)]
        if targeted:
            for index, profile in enumerate(targeted, start=1):
                profile_source = str(profile.get("source") or source)
                symbol = str(profile.get("symbol") or fallback_symbol)
                timeframe = str(profile.get("timeframe") or fallback_timeframe)
                if not symbol or not timeframe:
                    continue
                params = {**base_params, **_dict(profile.get("params"))}
                profile_id = f"{name}:{profile_source}:{symbol}:{timeframe}"
                if profile_id in seen:
                    profile_id = f"{profile_id}:{index}"
                seen.add(profile_id)
                profiles.append(
                    _strategy_profile_record(
                        spec,
                        profile_id=profile_id,
                        source=profile_source,
                        symbol=symbol,
                        timeframe=timeframe,
                        params=params,
                        profile_source="targeted_params",
                        tuned=True,
                    )
                )
            continue
        if not fallback_symbol or not fallback_timeframe:
            continue
        profile_id = f"{name}:{source}:{fallback_symbol}:{fallback_timeframe}"
        if profile_id in seen:
            continue
        seen.add(profile_id)
        profiles.append(
            _strategy_profile_record(
                spec,
                profile_id=profile_id,
                source=source,
                symbol=fallback_symbol,
                timeframe=fallback_timeframe,
                params=base_params,
                profile_source="base_params",
                tuned=False,
            )
        )
    return profiles


def _strategy_profile_record(
    spec: dict[str, Any],
    *,
    profile_id: str,
    source: str,
    symbol: str,
    timeframe: str,
    params: dict[str, Any],
    profile_source: str,
    tuned: bool,
) -> dict[str, Any]:
    name = str(spec.get("name") or "")
    return {
        "profile_id": profile_id,
        "display_name": f"{symbol} {timeframe} - {name}",
        "strategy_name": name,
        "family": spec.get("family"),
        "description": spec.get("description"),
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "params": _bounded_mapping(params),
        "profile_source": profile_source,
        "tuned": tuned,
        "supported_market_types": _list(spec.get("supported_market_types")),
        "minimum_rows_policy": _bounded_mapping(spec.get("minimum_rows_policy")),
    }


def _configured_strategy_map(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    quant = config.get("quant") if isinstance(config.get("quant"), dict) else {}
    strategies = quant.get("strategies") if isinstance(quant.get("strategies"), list) else []
    result = {}
    for strategy in strategies:
        if not isinstance(strategy, dict) or strategy.get("enabled", True) is False:
            continue
        name = strategy.get("name")
        if isinstance(name, str) and name:
            result[name] = strategy
    return result


def _configured_strategy_families(specs: list[dict[str, Any]]) -> list[str]:
    return sorted({str(spec.get("family")) for spec in specs if spec.get("family")})


def _configured_market_types(specs: list[dict[str, Any]]) -> list[str]:
    values = {
        str(market_type)
        for spec in specs
        for market_type in _list(spec.get("supported_market_types"))
        if market_type
    }
    return sorted(values)


def _configured_symbols(config: dict[str, Any]) -> list[str]:
    market = config.get("market") if isinstance(config.get("market"), dict) else {}
    values = market.get("symbols") if isinstance(market.get("symbols"), list) else []
    symbols = []
    seen = set()
    for value in values:
        if not isinstance(value, str) or not value or value in seen:
            continue
        symbols.append(value)
        seen.add(value)
    return symbols


def _configured_ohlcv_sources(config: dict[str, Any]) -> list[str]:
    market = config.get("market") if isinstance(config.get("market"), dict) else {}
    ohlcv = market.get("ohlcv") if isinstance(market.get("ohlcv"), dict) else {}
    values = ohlcv.get("sources") if isinstance(ohlcv.get("sources"), list) else []
    configured = {str(value) for value in values if isinstance(value, str) and value}
    if not configured:
        configured = set(OHLCV_SOURCE_ORDER)
    return [source for source in OHLCV_SOURCE_ORDER if source in configured]


def _configured_timeframes(config: dict[str, Any]) -> list[str]:
    market = config.get("market") if isinstance(config.get("market"), dict) else {}
    ohlcv = market.get("ohlcv") if isinstance(market.get("ohlcv"), dict) else {}
    values = ohlcv.get("timeframes") if isinstance(ohlcv.get("timeframes"), list) else []
    configured = {str(value) for value in values if isinstance(value, str) and value}
    return [timeframe for timeframe in OHLCV_TIMEFRAME_ORDER if timeframe in configured]


def _selected_run(config_path: Path, *, base: Path, run_id: str | None) -> dict[str, Any]:
    index_path = run_index_path(config_path)
    if not index_path.exists():
        return _section(
            "selected_run",
            "missing",
            fields={"run_id": run_id},
            source_artifacts=[RUN_INDEX_ARTIFACT],
            warnings=["local run index was not found."],
        )
    try:
        with closing(sqlite3.connect(index_path)) as connection:
            record = fetch_run_index_record(connection, run_id) if run_id else None
            if run_id is None:
                selected = select_latest_run_record(connection)
                record = selected.run if selected else None
    except sqlite3.Error as exc:
        return _section(
            "selected_run",
            "failed",
            fields={"run_id": run_id},
            source_artifacts=[RUN_INDEX_ARTIFACT],
            errors=[f"{RUN_INDEX_ARTIFACT} is not readable: {exc}"],
        )
    if record is None:
        warning = "run id was not found in the local run index." if run_id else "local run index does not contain a latest run."
        return _section(
            "selected_run",
            "missing",
            fields={"run_id": run_id},
            source_artifacts=[RUN_INDEX_ARTIFACT],
            warnings=[warning],
        )

    manifest_path = _resolve_ref(record.manifest_path, base=base)
    manifest, error = _read_json(manifest_path)
    run_dir = _resolve_ref(record.run_dir, base=base)
    fields = {
        "run_id": record.run_id,
        "run_dir": _safe_ref(run_dir, base=base),
        "manifest": _safe_ref(manifest_path, base=base),
    }
    if error:
        return _section(
            "selected_run",
            "failed",
            fields=fields,
            source_artifacts=[RUN_INDEX_ARTIFACT, fields["manifest"]],
            errors=[error],
        )
    fields.update(
        {
            "run_status": str(manifest.get("status") or "unknown"),
            "started_at": manifest.get("started_at"),
            "finished_at": manifest.get("finished_at"),
        }
    )
    return _section(
        "selected_run",
        "available",
        fields=fields,
        source_artifacts=[RUN_INDEX_ARTIFACT, fields["manifest"]],
        extra={"run_dir_path": run_dir, "manifest": manifest},
    )


def _pipeline_strategy_section(selected_run: dict[str, Any], *, base: Path) -> dict[str, Any]:
    if selected_run["status"] != "available":
        return _section(
            "pipeline_strategy_artifacts",
            "missing",
            source_artifacts=selected_run["source_artifacts"],
            warnings=["selected run is not available."],
        )
    run_dir = selected_run["run_dir_path"]
    manifest = selected_run["manifest"]
    artifacts = [
        _pipeline_artifact_summary(name, default_artifact, run_dir=run_dir, manifest=manifest, base=base)
        for name, default_artifact in PIPELINE_STRATEGY_ARTIFACTS
    ]
    statuses = [artifact["status"] for artifact in artifacts]
    return _section(
        "pipeline_strategy_artifacts",
        _overall_status(statuses),
        fields={
            "run_id": selected_run["fields"]["run_id"],
            "artifact_count": len(artifacts),
            "available_artifacts": sum(1 for status in statuses if status == "available"),
        },
        source_artifacts=sorted(
            {
                artifact
                for summary in artifacts
                for artifact in _string_list(summary.get("source_artifacts"))
            }
        ),
        warnings=[
            warning
            for summary in artifacts
            for warning in _string_list(summary.get("warnings"))
        ],
        errors=[
            error
            for summary in artifacts
            for error in _string_list(summary.get("errors"))
        ],
        extra={"artifacts": artifacts},
    )


def _pipeline_artifact_summary(
    name: str,
    default_artifact: str,
    *,
    run_dir: Path,
    manifest: dict[str, Any],
    base: Path,
) -> dict[str, Any]:
    artifact = _artifact_ref(manifest, name, default_artifact)
    if artifact is None:
        return _artifact_section(name, "missing", artifact=default_artifact, warnings=[f"{name} artifact is not recorded."])
    path = run_dir / artifact
    preview_path = _safe_ref(path, base=base)
    data, error = _read_json(path)
    if error:
        status = "missing" if "was not found" in error else "failed"
        return _artifact_section(
            name,
            status,
            artifact=artifact,
            preview_path=preview_path,
            source_artifacts=[preview_path],
            errors=[error] if status == "failed" else [],
            warnings=[error] if status == "missing" else [],
        )
    status = _artifact_status(data)
    return _artifact_section(
        name,
        status,
        artifact=artifact,
        preview_path=preview_path,
        fields=_artifact_fields(name, data),
        records=_bounded_records(name, data),
        source_artifacts=[preview_path, *_source_artifacts(data)],
        warnings=_messages(data.get("warnings")),
        errors=_messages(data.get("errors")),
    )


def _standalone_strategy_section(
    config: dict[str, Any],
    *,
    config_path: Path,
    base: Path,
) -> dict[str, Any]:
    output_root = _run_output_root(config, config_path=config_path)
    backtests = _standalone_backtests(output_root / "strategy_backtests", base=base)
    experiments = _standalone_experiments(output_root / "strategy_experiments", base=base)
    optimizations = _standalone_optimizations(output_root / "strategy_optimizations", base=base)
    standalone_items = [*backtests, *experiments, *optimizations]
    statuses = [item["status"] for item in standalone_items]
    if not statuses:
        status = "missing"
        warnings = ["standalone strategy backtest, experiment, and optimization output directories were not found."]
    else:
        status = _overall_status(statuses)
        warnings = []
    return _section(
        "standalone_strategy_outputs",
        status,
        fields={
            "output_root": _safe_ref(output_root, base=base),
            "backtest_count": len(backtests),
            "experiment_count": len(experiments),
            "optimization_count": len(optimizations),
            "max_items": MAX_STANDALONE_RUNS,
        },
        source_artifacts=sorted(
            {
                artifact
                for item in standalone_items
                for artifact in _string_list(item.get("source_artifacts"))
            }
        ),
        warnings=warnings
        + [
            warning
            for item in standalone_items
            for warning in _string_list(item.get("warnings"))
        ],
        errors=[
            error
            for item in standalone_items
            for error in _string_list(item.get("errors"))
        ],
        extra={"backtests": backtests, "experiments": experiments, "optimizations": optimizations},
    )


def _shared_strategy_history_section(config_path: Path, *, base: Path) -> dict[str, Any]:
    history = read_strategy_evaluation_history(config_path)
    records = _list(history.get("records"))
    backtests = [_shared_history_backtest(record, base=base) for record in records[:MAX_STANDALONE_RUNS]]
    status = _normalize_status(str(history.get("status") or "missing"))
    if records and status == "missing":
        status = "available"
    return _section(
        "shared_strategy_evaluation_history",
        status,
        fields={
            "history": STRATEGY_EVALUATION_HISTORY_ARTIFACT,
            "record_count": len(records),
            "backtest_count": len(backtests),
            "max_items": MAX_STANDALONE_RUNS,
        },
        source_artifacts=[STRATEGY_EVALUATION_HISTORY_ARTIFACT],
        warnings=_messages(history.get("warnings")),
        errors=_messages(history.get("errors")),
        extra={"backtests": backtests},
    )


def _shared_history_backtest(record: Any, *, base: Path) -> dict[str, Any]:
    item = _dict(record)
    source_artifacts = _safe_source_artifacts(_string_list(item.get("source_artifacts")), base=base)
    warnings = _messages(item.get("warnings"))
    return {
        "type": "strategy_backtest",
        "status": _normalize_status(str(item.get("status") or "unknown")),
        "output_dir": _shared_output_ref(item),
        "fields": {
            "created_at": item.get("created_at"),
            "execution_source": _bounded_mapping(item.get("execution_source")),
            "evaluation_id": item.get("evaluation_id"),
            "strategy_name": item.get("strategy_name"),
            "source": item.get("source"),
            "symbol": item.get("symbol"),
            "timeframe": item.get("timeframe"),
            "input_window_start": item.get("input_window_start"),
            "input_window_end": item.get("input_window_end"),
            "latest_candle_time": item.get("latest_candle_time"),
            "params": _bounded_mapping(item.get("params")),
            "metrics": _backtest_metrics(_dict(item.get("metrics"))),
        },
        "records": {},
        "visualization": _backtest_visualization(_dict(item)),
        "source_artifacts": source_artifacts,
        "warnings": warnings,
        "warning_groups": _warning_groups(warnings, source_artifacts),
        "errors": _messages(item.get("errors")),
    }


def _shared_output_ref(record: dict[str, Any]) -> str:
    source = _dict(record.get("execution_source"))
    return str(source.get("output_dir") or source.get("run_dir") or record.get("history_id") or "shared_history")


def _safe_source_artifacts(values: list[str], *, base: Path) -> list[str]:
    safe = []
    for value in values:
        path = _resolve_ref(value, base=base)
        safe.append(_safe_ref(path, base=base))
    return safe


def _standalone_backtests(root: Path, *, base: Path) -> list[dict[str, Any]]:
    return [
        _standalone_backtest_summary(path, base=base)
        for path in _standalone_dirs(root)
    ]


def _standalone_experiments(root: Path, *, base: Path) -> list[dict[str, Any]]:
    return [
        _standalone_experiment_summary(path, base=base)
        for path in _standalone_dirs(root)
    ]


def _standalone_optimizations(root: Path, *, base: Path) -> list[dict[str, Any]]:
    return [
        _standalone_optimization_summary(path, base=base)
        for path in _standalone_dirs(root)
    ]


def _standalone_dirs(root: Path) -> list[Path]:
    if not root.exists() or not root.is_dir():
        return []
    return sorted(
        [path for path in root.iterdir() if path.is_dir()],
        key=lambda path: path.name,
        reverse=True,
    )[:MAX_STANDALONE_RUNS]


def _standalone_backtest_summary(path: Path, *, base: Path) -> dict[str, Any]:
    manifest_path = path / "manifest.json"
    artifact_path = path / "strategy_backtest.json"
    manifest, manifest_error = _read_json(manifest_path)
    artifact, artifact_error = _read_json(artifact_path)
    source_artifacts = [_safe_ref(manifest_path, base=base), _safe_ref(artifact_path, base=base)]
    if manifest_error:
        return _standalone_item(
            "strategy_backtest",
            path=path,
            status="missing" if "was not found" in manifest_error else "failed",
            base=base,
            source_artifacts=source_artifacts,
            warnings=[manifest_error] if "was not found" in manifest_error else [],
            errors=[] if "was not found" in manifest_error else [manifest_error],
        )
    errors = [artifact_error] if artifact_error and "was not found" not in artifact_error else []
    warnings = [artifact_error] if artifact_error and "was not found" in artifact_error else []
    status = _manifest_status(manifest, artifact, artifact_error)
    return _standalone_item(
        "strategy_backtest",
        path=path,
        status=status,
        base=base,
        fields={
            "created_at": manifest.get("created_at"),
            "status": manifest.get("status"),
            "evaluation_status": manifest.get("evaluation_status"),
            "inputs": _bounded_mapping(manifest.get("inputs")),
            "metrics": _backtest_metrics(artifact),
            "equity_curve_points": _list_count(artifact.get("equity_curve")),
        },
        visualization=_backtest_visualization(artifact),
        source_artifacts=source_artifacts + _source_artifacts(manifest),
        warnings=[*_messages(manifest.get("warnings")), *warnings],
        errors=[*_messages(manifest.get("errors")), *errors],
    )


def _standalone_experiment_summary(path: Path, *, base: Path) -> dict[str, Any]:
    manifest_path = path / "manifest.json"
    experiment_path = path / "strategy_experiment.json"
    benchmark_path = path / "strategy_benchmark_suite.json"
    gates_path = path / "strategy_effectiveness_gates.json"
    manifest, manifest_error = _read_json(manifest_path)
    experiment, experiment_error = _read_json(experiment_path)
    benchmark, benchmark_error = _read_json(benchmark_path)
    gates, gates_error = _read_json(gates_path)
    source_artifacts = [
        _safe_ref(manifest_path, base=base),
        _safe_ref(experiment_path, base=base),
        _safe_ref(benchmark_path, base=base),
        _safe_ref(gates_path, base=base),
    ]
    if manifest_error:
        return _standalone_item(
            "strategy_experiment",
            path=path,
            status="missing" if "was not found" in manifest_error else "failed",
            base=base,
            source_artifacts=source_artifacts,
            warnings=[manifest_error] if "was not found" in manifest_error else [],
            errors=[] if "was not found" in manifest_error else [manifest_error],
        )
    artifact_errors = [error for error in (experiment_error, benchmark_error, gates_error) if error]
    status = _manifest_status(manifest, experiment, artifact_errors[0] if artifact_errors else None)
    if any(error and "is not valid JSON" in error for error in artifact_errors):
        status = "failed"
    return _standalone_item(
        "strategy_experiment",
        path=path,
        status=status,
        base=base,
        fields={
            "created_at": manifest.get("created_at"),
            "status": manifest.get("status"),
            "inputs": _bounded_mapping(manifest.get("inputs")),
            "counts": _bounded_mapping(manifest.get("counts")),
            "coverage": _bounded_mapping(experiment.get("coverage")),
            "benchmark_coverage": _bounded_mapping(benchmark.get("coverage")),
            "gate_coverage": _bounded_mapping(gates.get("coverage")),
        },
        records={
            "candidates": _candidate_records(experiment.get("candidates")),
            "gates": _gate_records(gates.get("records")),
            "benchmarks": _benchmark_records(benchmark.get("benchmarks")),
        },
        source_artifacts=source_artifacts + _source_artifacts(manifest),
        warnings=[
            *_messages(manifest.get("warnings")),
            *_messages(experiment.get("warnings")),
            *_messages(gates.get("warnings")),
            *[error for error in artifact_errors if "was not found" in error],
        ],
        errors=[
            *_messages(manifest.get("errors")),
            *_messages(experiment.get("errors")),
            *_messages(gates.get("errors")),
            *[error for error in artifact_errors if "was not found" not in error],
        ],
    )


def _standalone_optimization_summary(path: Path, *, base: Path) -> dict[str, Any]:
    manifest_path = path / "manifest.json"
    optimization_path = path / "strategy_optimization.json"
    benchmark_path = path / "strategy_benchmark_suite.json"
    manifest, manifest_error = _read_json(manifest_path)
    optimization, optimization_error = _read_json(optimization_path)
    benchmark, benchmark_error = _read_json(benchmark_path)
    source_artifacts = [
        _safe_ref(manifest_path, base=base),
        _safe_ref(optimization_path, base=base),
        _safe_ref(benchmark_path, base=base),
    ]
    if manifest_error:
        return _standalone_item(
            "strategy_optimization",
            path=path,
            status="missing" if "was not found" in manifest_error else "failed",
            base=base,
            source_artifacts=source_artifacts,
            warnings=[manifest_error] if "was not found" in manifest_error else [],
            errors=[] if "was not found" in manifest_error else [manifest_error],
        )
    artifact_errors = [error for error in (optimization_error, benchmark_error) if error]
    status = _manifest_status(manifest, optimization, artifact_errors[0] if artifact_errors else None)
    if any(error and "is not valid JSON" in error for error in artifact_errors):
        status = "failed"
    robustness = _dict(optimization.get("robustness"))
    walk_forward = _dict(optimization.get("walk_forward"))
    return _standalone_item(
        "strategy_optimization",
        path=path,
        status=status,
        base=base,
        fields={
            "created_at": manifest.get("created_at"),
            "status": manifest.get("status"),
            "strategy_name": optimization.get("strategy_name"),
            "target": _bounded_mapping(optimization.get("target")),
            "parameter_profile": _bounded_mapping(optimization.get("parameter_profile")),
            "counts": _bounded_mapping(manifest.get("counts")),
            "search_space": _bounded_mapping(optimization.get("search_space")),
            "coverage": _bounded_mapping(optimization.get("coverage")),
            "benchmark_coverage": _bounded_mapping(benchmark.get("coverage")),
            "selected_candidate": _optimization_selected_candidate(optimization.get("selected_candidate")),
            "recommended_targeted_params": _bounded_mapping(optimization.get("recommended_targeted_params")),
            "robustness": _bounded_mapping(robustness),
            "walk_forward": _walk_forward_summary(walk_forward),
        },
        records={
            "failed_candidates": _optimization_failed_candidates(optimization.get("failed_candidates")),
        },
        source_artifacts=source_artifacts + _source_artifacts(manifest),
        warnings=[
            *_messages(manifest.get("warnings")),
            *_messages(optimization.get("warnings")),
            *_messages(robustness.get("warnings")),
            *_messages(walk_forward.get("warnings")),
            *[error for error in artifact_errors if "was not found" in error],
        ],
        errors=[
            *_messages(manifest.get("errors")),
            *_messages(optimization.get("errors")),
            *_messages(robustness.get("errors")),
            *_messages(walk_forward.get("errors")),
            *[error for error in artifact_errors if "was not found" not in error],
        ],
    )


def _artifact_fields(name: str, data: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "artifact_type": data.get("artifact_type"),
        "artifact_status": data.get("status"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "warning_count": len(_list(data.get("warnings"))),
        "error_count": len(_list(data.get("errors"))),
    }
    for key in ("counts", "coverage", "inputs", "policy"):
        bounded = _bounded_mapping(data.get(key))
        if bounded:
            fields[key] = bounded
    if name == "strategy_lifecycle_state":
        counts = _bounded_mapping(data.get("counts"))
        if counts:
            fields["lifecycle_counts"] = counts
    for key in ("runs", "records", "candidates", "benchmarks"):
        count = _list_count(data.get(key))
        if count:
            fields[f"{key}_count"] = count
            fields[f"{key}_status_counts"] = _status_counts(data.get(key))
    return {key: value for key, value in fields.items() if value is not None}


def _bounded_records(name: str, data: dict[str, Any]) -> dict[str, Any]:
    if name == "strategy_benchmark_suite":
        return {"benchmarks": _benchmark_records(data.get("benchmarks"))}
    if name == "quant_strategy_runs":
        return {"runs": _quant_run_records(data.get("runs"))}
    if name == "strategy_evaluation_summary":
        return {"records": _evaluation_records(data.get("records"))}
    if name == "strategy_experiment":
        return {"candidates": _candidate_records(data.get("candidates"))}
    if name == "strategy_effectiveness_gates":
        return {"gates": _gate_records(data.get("records"))}
    if name == "strategy_lifecycle_state":
        return {"lifecycle": _lifecycle_records(data.get("records"))}
    return {}


def _benchmark_records(value: Any) -> list[dict[str, Any]]:
    return [
        {
            "benchmark_id": item.get("benchmark_id"),
            "status": item.get("status"),
            "source": item.get("source"),
            "symbol": item.get("symbol"),
            "timeframe": item.get("timeframe"),
            "window_identity": item.get("window_identity"),
            "input_window_start": item.get("input_window_start"),
            "input_window_end": item.get("input_window_end"),
            "row_count": item.get("row_count"),
        }
        for item in _dict_items(value)[:MAX_SUMMARY_ITEMS]
    ]


def _quant_run_records(value: Any) -> list[dict[str, Any]]:
    records = []
    for item in _dict_items(value)[:MAX_SUMMARY_ITEMS]:
        backtest = _dict(item.get("backtest_diagnostic"))
        parameter = _dict(item.get("parameter_diagnostic"))
        records.append(
            {
                "strategy_run_id": item.get("strategy_run_id"),
                "strategy_name": item.get("strategy_name"),
                "strategy_version": item.get("strategy_version"),
                "status": item.get("status"),
                "source": item.get("source"),
                "symbol": item.get("symbol"),
                "timeframe": item.get("timeframe"),
                "signal": _bounded_mapping(item.get("signal")),
                "summary": _bounded_mapping(item.get("summary")),
                "backtest_diagnostic": _quant_backtest_summary(backtest),
                "parameter_diagnostic": _quant_parameter_summary(parameter),
            }
        )
    return records


def _quant_backtest_summary(backtest: dict[str, Any]) -> dict[str, Any]:
    if not backtest:
        return {}
    return {
        "enabled": backtest.get("enabled"),
        "status": backtest.get("status"),
        "assumptions": _bounded_mapping(backtest.get("assumptions")),
        "metrics": _bounded_mapping(backtest.get("metrics")),
    }


def _quant_parameter_summary(parameter: dict[str, Any]) -> dict[str, Any]:
    if not parameter:
        return {}
    return {
        "enabled": parameter.get("enabled"),
        "status": parameter.get("status"),
        "assumptions": _bounded_mapping(parameter.get("assumptions")),
        "signal_state_stability": _bounded_mapping(parameter.get("signal_state_stability")),
        "performance_stability": _bounded_mapping(parameter.get("performance_stability")),
        "summary_metrics": _bounded_mapping(parameter.get("summary_metrics")),
    }


def _evaluation_records(value: Any) -> list[dict[str, Any]]:
    records = []
    for item in _dict_items(value)[:MAX_SUMMARY_ITEMS]:
        single_window = _dict(item.get("single_window"))
        records.append(
            {
                "evaluation_id": item.get("evaluation_id"),
                "strategy_name": item.get("strategy_name"),
                "strategy_version": item.get("strategy_version"),
                "status": item.get("status"),
                "source": item.get("source"),
                "symbol": item.get("symbol"),
                "timeframe": item.get("timeframe"),
                "strategy_metrics": _bounded_mapping(single_window.get("strategy_metrics")),
                "baseline_metrics": _bounded_mapping(single_window.get("baseline_metrics")),
                "relative_metrics": _bounded_mapping(single_window.get("relative_metrics")),
                "trade_summary": _bounded_mapping(single_window.get("trade_summary")),
                "walk_forward": _walk_forward_summary(item.get("walk_forward")),
                "parameter_stability": _bounded_mapping(item.get("parameter_stability")),
                "overfitting_risk": _bounded_mapping(item.get("overfitting_risk")),
                "assessment": _bounded_mapping(item.get("assessment")),
            }
        )
    return records


def _candidate_records(value: Any) -> list[dict[str, Any]]:
    records = []
    for item in _dict_items(value)[:MAX_SUMMARY_ITEMS]:
        evaluations = _dict_items(item.get("evaluations"))
        records.append(
            {
                "strategy_name": item.get("strategy_name"),
                "status": item.get("status"),
                "summary": _bounded_mapping(item.get("summary")),
                "evaluation_count": len(evaluations),
                "evaluation_status_counts": _status_counts(evaluations),
            }
        )
    return records


def _optimization_selected_candidate(value: Any) -> dict[str, Any]:
    item = _dict(value)
    if not item:
        return {}
    return {
        "candidate_id": item.get("candidate_id"),
        "status": item.get("status"),
        "strategy_name": item.get("strategy_name"),
        "params": _bounded_mapping(item.get("params")),
        "changed_params": _bounded_mapping(item.get("changed_params")),
        "metrics": _bounded_mapping(item.get("metrics")),
        "parameter_profile": _bounded_mapping(item.get("parameter_profile")),
        "summary": _bounded_mapping(item.get("summary")),
        "automatic_config_mutation": item.get("automatic_config_mutation"),
    }


def _optimization_failed_candidates(value: Any) -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": item.get("candidate_id"),
            "error_type": item.get("error_type"),
            "message": item.get("message"),
        }
        for item in _dict_items(value)[:MAX_SUMMARY_ITEMS]
    ]


def _gate_records(value: Any) -> list[dict[str, Any]]:
    records = []
    for item in _dict_items(value)[:MAX_SUMMARY_ITEMS]:
        records.append(
            {
                "gate_id": item.get("gate_id"),
                "strategy_name": item.get("strategy_name"),
                "status": item.get("status"),
                "source": item.get("source"),
                "symbol": item.get("symbol"),
                "timeframe": item.get("timeframe"),
                "reason_codes": [
                    str(reason.get("code"))
                    for reason in _dict_items(item.get("reasons"))[:MAX_SUMMARY_ITEMS]
                    if reason.get("code")
                ],
                "gate_inputs": _bounded_mapping(item.get("gate_inputs")),
            }
        )
    return records


def _lifecycle_records(value: Any) -> list[dict[str, Any]]:
    records = []
    for item in _dict_items(value)[:MAX_SUMMARY_ITEMS]:
        scope = _dict(item.get("scope"))
        records.append(
            {
                "lifecycle_record_id": item.get("lifecycle_record_id"),
                "strategy_name": scope.get("strategy_name") or item.get("strategy_name"),
                "source": scope.get("source") or item.get("source"),
                "symbol": scope.get("symbol") or item.get("symbol"),
                "timeframe": scope.get("timeframe") or item.get("timeframe"),
                "lifecycle_status": item.get("lifecycle_status"),
                "degradation_state": _dict(item.get("degradation")).get("state"),
                "health_state": _dict(item.get("health_state")).get("state"),
                "retirement_state": _dict(item.get("retirement")).get("state"),
                "strategy_contract_version": item.get("strategy_contract_version"),
                "parameter_version": item.get("parameter_version"),
            }
        )
    return records


def _walk_forward_summary(value: Any) -> dict[str, Any]:
    data = _dict(value)
    summary = _bounded_mapping(data.get("summary"))
    return {
        "enabled": data.get("enabled"),
        "status": data.get("status"),
        "summary": summary,
        "window_count": _list_count(data.get("windows")),
    }


def _backtest_metrics(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_metrics": _bounded_mapping(artifact.get("strategy_metrics")),
        "baseline_metrics": _bounded_mapping(artifact.get("baseline_metrics")),
        "relative_metrics": _bounded_mapping(artifact.get("relative_metrics")),
        "trade_summary": _bounded_mapping(artifact.get("trade_summary")),
        "sample": _bounded_mapping(artifact.get("sample")),
        "execution_model": _bounded_mapping(artifact.get("execution_model")),
        "cost_assumptions": _bounded_mapping(artifact.get("cost_assumptions")),
    }


def _backtest_visualization(artifact: dict[str, Any]) -> dict[str, Any]:
    raw = artifact.get("visualization")
    if not isinstance(raw, dict):
        return {}
    bars = [_bounded_bar(item) for item in _list(raw.get("bars"))]
    bars = [item for item in bars if item]
    markers = [_bounded_marker(item) for item in _list(raw.get("markers"))]
    markers = [item for item in markers if item]
    reconstructed_markers = _position_transition_markers(
        artifact.get("equity_curve"),
        raw_markers=markers,
        execution_model=_dict(artifact.get("execution_model")),
    )
    if len(reconstructed_markers) > len(markers):
        markers = reconstructed_markers
    equity_curve = [_bounded_equity_point(item) for item in _list(raw.get("equity_curve"))]
    equity_curve = [item for item in equity_curve if item]
    visible_markers = markers[-MAX_BACKTEST_VISUALIZATION_MARKERS:]
    omitted = _bounded_mapping(raw.get("omitted"))
    total_marker_count = len(markers) or _position_transition_marker_count(artifact.get("equity_curve"))
    if total_marker_count:
        omitted["markers"] = max(0, total_marker_count - len(visible_markers))
    return {
        "schema_version": raw.get("schema_version", 1),
        "chart_type": raw.get("chart_type", "candlestick_backtest"),
        "status": _normalize_status(str(raw.get("status") or "partial")),
        "strategy_name": raw.get("strategy_name"),
        "source": raw.get("source"),
        "symbol": raw.get("symbol"),
        "timeframe": raw.get("timeframe"),
        "bars": bars[-MAX_BACKTEST_VISUALIZATION_BARS:],
        "markers": visible_markers,
        "equity_curve": equity_curve[-MAX_BACKTEST_VISUALIZATION_EQUITY_POINTS:],
        "limits": {
            "max_bars": MAX_BACKTEST_VISUALIZATION_BARS,
            "max_markers": MAX_BACKTEST_VISUALIZATION_MARKERS,
            "max_equity_points": MAX_BACKTEST_VISUALIZATION_EQUITY_POINTS,
        },
        "omitted": omitted,
        "warnings": _messages(raw.get("warnings")),
    }


def _position_transition_marker_count(value: Any) -> int:
    markers = 0
    previous_position = 0.0
    for point in _dict_items(value):
        try:
            position = float(point.get("position") or 0.0)
        except (TypeError, ValueError):
            continue
        if position != previous_position:
            markers += 1
        previous_position = position
    return markers


def _position_transition_markers(
    value: Any,
    *,
    raw_markers: list[dict[str, Any]],
    execution_model: dict[str, Any],
) -> list[dict[str, Any]]:
    raw_by_time = {str(marker.get("time")): marker for marker in raw_markers if marker.get("time")}
    execution_timing = execution_model.get("position_timing") or execution_model.get("execution_timing")
    markers = []
    previous_position = 0.0
    for point in _dict_items(value):
        try:
            position = float(point.get("position") or 0.0)
        except (TypeError, ValueError):
            continue
        if position == previous_position:
            previous_position = position
            continue
        time = _equity_point_time(point)
        if not time:
            previous_position = position
            continue
        marker = _position_marker(time, previous_position=previous_position, position=position)
        if execution_timing:
            marker["execution_timing"] = execution_timing
        raw_marker = raw_by_time.get(str(time), {})
        for key in ("price", "cost", "funding", "source_ref"):
            if raw_marker.get(key) is not None:
                marker[key] = raw_marker[key]
        if raw_marker.get("warnings"):
            marker["warnings"] = raw_marker["warnings"]
        markers.append(_bounded_marker(marker))
        previous_position = position
    return [marker for marker in markers if marker]


def _equity_point_time(point: dict[str, Any]) -> Any:
    return point.get("time") or point.get("open_time") or point.get("timestamp")


def _position_marker(time: Any, *, previous_position: float, position: float) -> dict[str, Any]:
    if position == 0:
        side = "long" if previous_position > 0 else "short"
        label = "Sell" if previous_position > 0 else "Cover"
        kind = "exit"
    elif previous_position == 0:
        side = "long" if position > 0 else "short"
        label = "Long" if position > 0 else "Short"
        kind = "entry"
    else:
        side = "long" if position > 0 else "short"
        label = "Long" if position > 0 else "Short"
        kind = "rebalance"
    return {
        "time": time,
        "kind": kind,
        "label": label,
        "side": side,
        "position": position,
        "exposure": abs(position),
    }


def _bounded_bar(value: Any) -> dict[str, Any]:
    item = _dict(value)
    if not item:
        return {}
    return {
        "time": item.get("time"),
        "open": item.get("open"),
        "high": item.get("high"),
        "low": item.get("low"),
        "close": item.get("close"),
        "volume": item.get("volume"),
    }


def _bounded_marker(value: Any) -> dict[str, Any]:
    item = _dict(value)
    if not item:
        return {}
    return {
        "time": item.get("time"),
        "kind": item.get("kind"),
        "label": item.get("label"),
        "side": item.get("side"),
        "position": item.get("position"),
        "exposure": item.get("exposure"),
        "execution_timing": item.get("execution_timing"),
        "price": item.get("price"),
        "cost": item.get("cost"),
        "funding": item.get("funding"),
        "source_ref": item.get("source_ref"),
        "warnings": _messages(item.get("warnings"))[:MAX_WARNING_GROUPS],
    }


def _bounded_equity_point(value: Any) -> dict[str, Any]:
    item = _dict(value)
    if not item:
        return {}
    return {
        "time": _equity_point_time(item),
        "net_equity": item.get("net_equity"),
        "gross_equity": item.get("gross_equity"),
        "position": item.get("position"),
        "turnover": item.get("turnover"),
    }


def _artifact_status(data: dict[str, Any]) -> str:
    raw_status = data.get("status")
    if isinstance(raw_status, str) and raw_status:
        return _normalize_status(raw_status)
    if _list(data.get("errors")):
        return "failed"
    if _list(data.get("warnings")):
        return "warning"
    return "available"


def _manifest_status(manifest: dict[str, Any], artifact: dict[str, Any], artifact_error: str | None) -> str:
    if artifact_error and "was not found" not in artifact_error:
        return "failed"
    manifest_status = manifest.get("status")
    if isinstance(manifest_status, str) and manifest_status:
        return _normalize_status(manifest_status)
    return _artifact_status(artifact)


def _standalone_item(
    item_type: str,
    *,
    path: Path,
    status: str,
    base: Path,
    fields: dict[str, Any] | None = None,
    records: dict[str, Any] | None = None,
    visualization: dict[str, Any] | None = None,
    source_artifacts: list[str] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    source_artifacts = source_artifacts or []
    warnings = warnings or []
    return {
        "type": item_type,
        "status": status,
        "output_dir": _safe_ref(path, base=base),
        "fields": fields or {},
        "records": records or {},
        "visualization": visualization or {},
        "source_artifacts": source_artifacts,
        "warnings": warnings,
        "warning_groups": _warning_groups(warnings, source_artifacts),
        "errors": errors or [],
    }


def _artifact_section(
    name: str,
    status: str,
    *,
    artifact: str,
    preview_path: str | None = None,
    fields: dict[str, Any] | None = None,
    records: dict[str, Any] | None = None,
    source_artifacts: list[str] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    source_artifacts = source_artifacts or []
    warnings = warnings or []
    return {
        "name": name,
        "status": status,
        "artifact": artifact,
        "preview_path": preview_path,
        "fields": fields or {},
        "records": records or {},
        "source_artifacts": source_artifacts,
        "warnings": warnings,
        "warning_groups": _warning_groups(warnings, source_artifacts),
        "errors": errors or [],
    }


def _section(
    name: str,
    status: str,
    *,
    fields: dict[str, Any] | None = None,
    source_artifacts: list[str] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_artifacts = source_artifacts or []
    warnings = warnings or []
    section = {
        "name": name,
        "status": status,
        "fields": fields or {},
        "source_artifacts": source_artifacts,
        "warnings": warnings,
        "warning_groups": _warning_groups(warnings, source_artifacts),
        "errors": errors or [],
    }
    if extra:
        section.update(extra)
    return section


def _artifact_ref(manifest: dict[str, Any], key: str, default: str) -> str | None:
    artifacts = manifest.get("artifacts")
    if isinstance(artifacts, dict):
        value = artifacts.get(key)
        if isinstance(value, str) and value:
            return value
    return default if manifest else None


def _run_output_root(config: dict[str, Any], *, config_path: Path) -> Path:
    run_config = config.get("run") if isinstance(config.get("run"), dict) else {}
    output_dir = Path(str(run_config.get("output_dir") or "runs"))
    return output_dir if output_dir.is_absolute() else _artifact_base(config_path) / output_dir


def _read_json(path: Path) -> tuple[dict[str, Any], str | None]:
    return read_json_object(path, external_ref_name=REJECTED_EXTERNAL_REF_NAME)


def _resolve_ref(value: str, *, base: Path) -> Path:
    return resolve_local_ref(value, base=base, rejected_name=REJECTED_EXTERNAL_REF_NAME)


def _safe_ref(path: Path, *, base: Path) -> str:
    return safe_local_ref(
        path,
        base=base,
        external_ref=EXTERNAL_ARTIFACT_REF,
        rejected_name=REJECTED_EXTERNAL_REF_NAME,
    )


def _source_artifacts(data: dict[str, Any]) -> list[str]:
    return _string_list(data.get("source_artifacts"))[:MAX_SUMMARY_ITEMS]


def _messages(value: Any) -> list[str]:
    messages = []
    for item in _list(value):
        if isinstance(item, str):
            messages.append(item)
        elif isinstance(item, dict):
            message = item.get("message") or item.get("code") or item.get("error_type")
            if message:
                messages.append(str(message))
    return messages


def _warning_groups(warnings: list[str], source_artifacts: list[str] | None = None) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    sources = sorted({source for source in (source_artifacts or []) if isinstance(source, str) and source})
    for warning in warnings:
        if not isinstance(warning, str):
            continue
        message = warning.strip()
        if not message:
            continue
        key = " ".join(message.lower().split())
        group = grouped.setdefault(
            key,
            {
                "message": message,
                "count": 0,
                "sources": sources[:MAX_WARNING_GROUP_SOURCES],
            },
        )
        group["count"] += 1
    return sorted(grouped.values(), key=lambda item: (-int(item["count"]), str(item["message"])))[:MAX_WARNING_GROUPS]


def _overall_status(statuses: list[str]) -> str:
    normalized = [_normalize_status(status) for status in statuses if status]
    if not normalized:
        return "missing"
    if any(status == "failed" for status in normalized):
        return "failed"
    if any(status == "degraded" for status in normalized):
        return "degraded"
    if any(status == "warning" for status in normalized):
        return "warning"
    if any(status == "available" for status in normalized):
        if any(status in {"missing", "partial", "skipped", "unknown"} for status in normalized):
            return "partial"
        return "available"
    if any(status == "partial" for status in normalized):
        return "partial"
    return "missing"


def _normalize_status(status: str) -> str:
    normalized = status.lower()
    if normalized in {"ok", "available", "succeeded", "success"}:
        return "available"
    if normalized in {"warning", "degraded", "failed", "partial", "missing", "skipped"}:
        return normalized
    if normalized in {"insufficient_data", "disabled", "not_generated", "not_run"}:
        return "partial"
    return "unknown"


def _status_counts(value: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in _dict_items(value):
        status = str(item.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _bounded_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    bounded: dict[str, Any] = {}
    for key, item in sorted(value.items()):
        if isinstance(item, (str, int, float, bool)) or item is None:
            bounded[str(key)] = item
    return bounded


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _list_count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0
