from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from halpha.config import load_config
from halpha.monitor.monitoring import MonitorSourceRefreshResult, run_monitor_source_cycle
from halpha.monitor.state_store import MONITOR_STATE_STORE_ARTIFACT, MonitorStateRepository


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_monitor_source_cycle_skips_pipeline_when_no_source_is_due(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, text_enabled=True)
    config = load_config(config_path)
    repository = MonitorStateRepository(config_path=config_path)
    repository.save_source_states(
        [
            {
                "source_key": "text",
                "enabled": True,
                "cadence_seconds": 60,
                "status": "no_change",
                "next_attempt_at": "2026-01-01T00:10:00Z",
            }
        ],
        monitor_output_dir="monitor",
        updated_at="2026-01-01T00:00:00Z",
    )

    def fail_pipeline(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("no due monitor sources must not run refresh_data")

    result = run_monitor_source_cycle(
        config,
        config_path=config_path,
        now=_time(),
        pipeline_runner=fail_pipeline,
    )

    health = repository.health_state(monitor_output_dir="monitor", base=tmp_path)

    assert result.succeeded is True
    assert result.status == "no_due_sources"
    assert result.run_id is None
    assert _product_run_dirs(tmp_path) == []
    assert _monitor_cycle_dirs(tmp_path) == []
    assert health["latest_cycle_id"] == result.cycle_id
    assert health["latest_cycle_status"] == "no_due_sources"
    assert health["latest_cycle_manifest"] == MONITOR_STATE_STORE_ARTIFACT
    states = {state["source_key"]: state for state in health["source_states"]}
    assert states["text"]["next_attempt_at"] == "2026-01-01T00:10:00Z"
    assert states["text"]["status"] == "no_change"
    assert states["macro_calendar"]["enabled"] is False


def test_monitor_source_cycle_isolates_source_failure_and_refreshes_other_due_sources(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, text_enabled=True, macro_enabled=True)
    config = load_config(config_path)
    calls: list[str] = []

    result = run_monitor_source_cycle(
        config,
        config_path=config_path,
        now=_time(),
        pipeline_runner=_decision_pipeline(tmp_path),
        source_refresher=_source_refresher(calls=calls, failed_sources={"text"}),
    )

    health = MonitorStateRepository(config_path=config_path).health_state(monitor_output_dir="monitor", base=tmp_path)
    states = {state["source_key"]: state for state in health["source_states"]}

    assert result.succeeded is True
    assert result.status == "partial"
    assert calls == ["macro_calendar", "text"]
    assert states["text"]["status"] == "failed"
    assert states["text"]["consecutive_failures"] == 1
    assert states["text"]["last_error"]["message"] == "simulated text failure"
    assert states["macro_calendar"]["status"] == "changed"
    assert states["macro_calendar"]["consecutive_failures"] == 0
    assert states["macro_calendar"]["latest_published_data_revision"]


def test_monitor_source_cycle_records_no_change_revision_without_broad_workflow(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, text_enabled=True)
    config = load_config(config_path)
    calls: list[str] = []

    first = run_monitor_source_cycle(
        config,
        config_path=config_path,
        now=_time(),
        pipeline_runner=_decision_pipeline(tmp_path),
        source_refresher=_source_refresher(calls=calls, revision="same-revision"),
    )
    runs_after_first = _product_run_dirs(tmp_path)
    cycle_dirs_after_first = _monitor_cycle_dirs(tmp_path)
    second = run_monitor_source_cycle(
        config,
        config_path=config_path,
        now=datetime(2026, 1, 1, 0, 2, tzinfo=timezone.utc),
        pipeline_runner=_decision_pipeline(tmp_path),
        source_refresher=_source_refresher(calls=calls, revision="same-revision"),
    )

    health = MonitorStateRepository(config_path=config_path).health_state(monitor_output_dir="monitor", base=tmp_path)
    states = {state["source_key"]: state for state in health["source_states"]}
    state = states["text"]

    assert first.status == "changed"
    assert runs_after_first == ["run-reassessment-1"]
    assert len(cycle_dirs_after_first) == 1
    assert second.status == "no_change"
    assert second.run_id is None
    assert _product_run_dirs(tmp_path) == runs_after_first
    assert _monitor_cycle_dirs(tmp_path) == cycle_dirs_after_first
    assert health["latest_cycle_id"] == second.cycle_id
    assert health["latest_cycle_status"] == "no_change"
    assert health["latest_cycle_manifest"] == MONITOR_STATE_STORE_ARTIFACT
    assert calls == ["text", "text"]
    assert state["source_key"] == "text"
    assert state["status"] == "no_change"
    assert state["changed_scope"] == {}
    assert state["latest_published_data_revision"] == "same-revision"


def test_monitor_source_cycle_keeps_multiple_no_change_sources_out_of_runs(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, text_enabled=True, macro_enabled=True)
    config = load_config(config_path)
    repository = MonitorStateRepository(config_path=config_path)
    repository.save_source_states(
        [
            {
                "source_key": "text",
                "enabled": True,
                "cadence_seconds": 60,
                "status": "changed",
                "next_attempt_at": "2026-01-01T00:00:00Z",
                "latest_published_data_revision": "text-revision",
            },
            {
                "source_key": "macro_calendar",
                "enabled": True,
                "cadence_seconds": 3600,
                "status": "changed",
                "next_attempt_at": "2026-01-01T00:00:00Z",
                "latest_published_data_revision": "macro-revision",
            },
        ],
        monitor_output_dir="monitor",
        updated_at="2026-01-01T00:00:00Z",
    )
    calls: list[str] = []

    def fail_pipeline(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("all-source no_change must not create a reassessment run")

    result = run_monitor_source_cycle(
        config,
        config_path=config_path,
        now=_time(),
        pipeline_runner=fail_pipeline,
        source_refresher=_source_refresher(
            calls=calls,
            revisions={
                "macro_calendar": "macro-revision",
                "text": "text-revision",
            },
        ),
    )

    health = repository.health_state(monitor_output_dir="monitor", base=tmp_path)
    states = {state["source_key"]: state for state in health["source_states"]}

    assert result.status == "no_change"
    assert result.run_id is None
    assert calls == ["macro_calendar", "text"]
    assert _product_run_dirs(tmp_path) == []
    assert _monitor_cycle_dirs(tmp_path) == []
    assert health["latest_cycle_id"] == result.cycle_id
    assert health["latest_cycle_status"] == "no_change"
    assert health["latest_cycle_manifest"] == MONITOR_STATE_STORE_ARTIFACT
    assert states["macro_calendar"]["status"] == "no_change"
    assert states["text"]["status"] == "no_change"
    assert states["macro_calendar"]["latest_published_data_revision"] == "macro-revision"
    assert states["text"]["latest_published_data_revision"] == "text-revision"


def test_monitor_source_cycle_batches_multiple_changed_sources_into_one_run(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, text_enabled=True, macro_enabled=True)
    config = load_config(config_path)
    calls: list[str] = []
    run_triggers: list[dict[str, Any]] = []

    result = run_monitor_source_cycle(
        config,
        config_path=config_path,
        now=_time(),
        pipeline_runner=_decision_pipeline(tmp_path, run_triggers=run_triggers),
        source_refresher=_source_refresher(calls=calls),
    )

    health = MonitorStateRepository(config_path=config_path).health_state(monitor_output_dir="monitor", base=tmp_path)
    states = {state["source_key"]: state for state in health["source_states"]}

    assert result.status == "changed"
    assert result.run_id == "run-reassessment-1"
    assert calls == ["macro_calendar", "text"]
    assert _product_run_dirs(tmp_path) == ["run-reassessment-1"]
    assert len(_monitor_cycle_dirs(tmp_path)) == 1
    assert health["latest_cycle_manifest"].startswith("monitor/cycles/")
    assert states["macro_calendar"]["status"] == "changed"
    assert states["text"]["status"] == "changed"
    assert states["macro_calendar"]["latest_run_id"] == "run-reassessment-1"
    assert states["text"]["latest_run_id"] == "run-reassessment-1"
    assert run_triggers == [
        {
            "source": "Monitor",
            "intent": "monitor_reassessment",
            "monitor_cycle_id": result.cycle_id,
            "source_keys": ["macro_calendar", "text"],
        }
    ]


def test_monitor_source_cycle_caps_per_source_failure_backoff(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, text_enabled=True)
    config = load_config(config_path)
    repository = MonitorStateRepository(config_path=config_path)
    repository.save_source_states(
        [
            {
                "source_key": "text",
                "enabled": True,
                "cadence_seconds": 60,
                "status": "failed",
                "next_attempt_at": "2026-01-01T00:00:00Z",
                "consecutive_failures": 3,
                "backoff_seconds": 240,
                "latest_published_data_revision": "previous-revision",
            }
        ],
        monitor_output_dir="monitor",
        updated_at="2026-01-01T00:00:00Z",
    )

    result = run_monitor_source_cycle(
        config,
        config_path=config_path,
        now=_time(),
        pipeline_runner=_decision_pipeline(tmp_path),
        source_refresher=_source_refresher(calls=[], failed_sources={"text"}),
    )

    health = repository.health_state(monitor_output_dir="monitor", base=tmp_path)
    states = {state["source_key"]: state for state in health["source_states"]}

    assert result.status == "partial"
    assert _product_run_dirs(tmp_path) == []
    assert len(_monitor_cycle_dirs(tmp_path)) == 1
    assert states["text"]["status"] == "failed"
    assert states["text"]["consecutive_failures"] == 4
    assert states["text"]["backoff_seconds"] == 300
    assert states["text"]["latest_published_data_revision"] == "previous-revision"


def test_monitor_source_cycle_prunes_file_backed_diagnostics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = _write_config(tmp_path, text_enabled=True)
    config = load_config(config_path)
    calls: list[str] = []
    source_refresher = _source_refresher(calls=calls)
    monkeypatch.setattr("halpha.monitor.monitoring.MONITOR_DIAGNOSTIC_CYCLE_DIR_LIMIT", 2)

    for index in range(3):
        run_monitor_source_cycle(
            config,
            config_path=config_path,
            now=datetime(2026, 1, 1, 0, index, tzinfo=timezone.utc),
            pipeline_runner=_decision_pipeline(tmp_path),
            source_refresher=source_refresher,
        )

    cycle_dirs = _monitor_cycle_dirs(tmp_path)

    assert len(cycle_dirs) == 2
    assert cycle_dirs == ["cycle-20260101T000100000000Z", "cycle-20260101T000200000000Z"]


def _write_config(
    tmp_path: Path,
    *,
    text_enabled: bool = False,
    macro_enabled: bool = False,
) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        f"""
run:
  output_dir: runs
  timezone: UTC
market:
  enabled: false
text:
  enabled: {str(text_enabled).lower()}
  sources:
    - name: feed
      type: rss
      url: https://example.invalid/feed.xml
macro_calendar:
  enabled: {str(macro_enabled).lower()}
  source: federal_reserve_fomc
  data_classes:
    - central_bank_event
  regions:
    - US
  lookback_days: 7
  lookahead_days: 45
report:
  language: zh-CN
codex:
  enabled: false
monitor:
  output_dir: monitor
  interval_seconds: 60
  failure_backoff_max_seconds: 300
  cooldown_seconds: 3600
""".strip(),
        encoding="utf-8",
    )
    return path


def _source_refresher(
    calls: list[str],
    failed_sources: set[str] | None = None,
    revision: str | None = None,
    revisions: dict[str, str] | None = None,
):
    counts: dict[str, int] = {}

    def refresh(config, *, config_path, group, started_at):  # noqa: ANN001
        source_key = _enabled_source(config)
        assert group.source_key == source_key
        calls.append(source_key)
        counts[source_key] = counts.get(source_key, 0) + 1
        if source_key in (failed_sources or set()):
            return MonitorSourceRefreshResult(
                succeeded=False,
                exit_code=3,
                failed_stage="refresh_data",
                reason=f"simulated {source_key} failure",
                revision=None,
                source_artifacts={},
                counts={},
                warnings=[],
            )
        return MonitorSourceRefreshResult(
            succeeded=True,
            exit_code=0,
            failed_stage=None,
            reason=None,
            revision=(revisions or {}).get(source_key) or revision or f"{source_key}-revision-{counts[source_key]}",
            source_artifacts={},
            counts={f"{source_key}_items": 1},
            warnings=[],
        )

    return refresh


def _decision_pipeline(tmp_path: Path, *, run_triggers: list[dict[str, Any]] | None = None):
    def pipeline(config, *, config_path, until_stage, skip_codex, run_trigger=None):  # noqa: ANN001
        assert until_stage == "build_materials"
        assert skip_codex is True
        if run_triggers is not None:
            run_triggers.append(dict(run_trigger or {}))
        return _run_result(tmp_path, source_key="reassessment", succeeded=True)

    return pipeline


def _enabled_source(config: dict[str, Any]) -> str:
    if config.get("text", {}).get("enabled"):
        return "text"
    if config.get("macro_calendar", {}).get("enabled"):
        return "macro_calendar"
    if config.get("onchain_flow", {}).get("enabled"):
        return "onchain_flow"
    derivatives = config.get("market", {}).get("derivatives")
    if isinstance(derivatives, dict) and derivatives.get("enabled"):
        return "derivatives"
    if config.get("market", {}).get("enabled"):
        return "market"
    raise AssertionError("one source group must be enabled")


def _run_result(
    tmp_path: Path,
    *,
    source_key: str,
    succeeded: bool,
    reason: str | None = None,
    revision: str | None = None,
):
    run_id = f"run-{source_key}-{len(list((tmp_path / 'runs').glob('*'))) + 1}"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(
        succeeded=succeeded,
        exit_code=0 if succeeded else 3,
        failed_stage=None if succeeded else "refresh_data",
        reason=reason,
        run=SimpleNamespace(
            run_id=run_id,
            run_dir=run_dir,
            manifest_path=run_dir / "run_manifest.json",
            manifest={
                "status": "succeeded" if succeeded else "failed",
                "stage_order": ["refresh_data"],
                "stages": [{"name": "refresh_data", "status": "succeeded" if succeeded else "failed"}],
                "artifacts": {source_key: f"raw/{source_key}.json"},
                "counts": {f"{source_key}_items": 1 if succeeded else 0},
                "monitor_source_revision": revision,
            },
        ),
    )


def _product_run_dirs(tmp_path: Path) -> list[str]:
    runs_dir = tmp_path / "runs"
    if not runs_dir.exists():
        return []
    return sorted(path.name for path in runs_dir.iterdir() if path.is_dir())


def _monitor_cycle_dirs(tmp_path: Path) -> list[str]:
    cycles_dir = tmp_path / "monitor" / "cycles"
    if not cycles_dir.exists():
        return []
    return sorted(path.name for path in cycles_dir.iterdir() if path.is_dir())


def _time() -> datetime:
    return datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
