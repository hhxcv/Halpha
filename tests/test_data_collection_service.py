from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from halpha.config import load_config
from halpha.data.data_collection_service import collect_research_data


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_configured_macro_collection_uses_refresh_data_pipeline_without_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_macro_config(tmp_path)
    config = load_config(config_path)
    calls: list[dict[str, Any]] = []

    def fake_run_pipeline(config_arg: dict[str, Any], **kwargs: Any) -> SimpleNamespace:
        calls.append({"config": config_arg, **kwargs})
        manifest_path = tmp_path / "runs" / "run-1" / "run_manifest.json"
        manifest_path.parent.mkdir(parents=True)
        manifest_path.write_text("{}", encoding="utf-8")
        run = SimpleNamespace(manifest_path=manifest_path)
        return SimpleNamespace(succeeded=True, exit_code=0, failed_stage=None, reason=None, run=run)

    monkeypatch.setattr("halpha.data.data_collection_service.run_pipeline", fake_run_pipeline)

    result = collect_research_data(
        config,
        config_path=config_path,
        data_type="macro_calendar",
        source=None,
        symbol=None,
        timeframe=None,
        requested_start="2026-06-01T00:00:00Z",
        requested_end="2026-06-03T00:00:00Z",
        apply=True,
        max_exact_windows=3,
        merge_gap_threshold_seconds=0,
        min_fetch_window_seconds=0,
        run_trigger={"source": "test", "intent": "data_collect"},
    )

    assert result["status"] == "ok"
    assert result["source"] == "configured"
    assert result["plan"]["strategy"] == "configured_scope"
    assert calls[0]["until_stage"] == "refresh_data"
    assert calls[0]["skip_codex"] is True
    assert "collect_market_data" in calls[0]["stage_handlers"]
    assert "collect_macro_calendar_data" not in calls[0]["stage_handlers"]
    assert "sync_macro_calendar_history" not in calls[0]["stage_handlers"]
    assert calls[0]["run_trigger"]["source"] == "test"


def _write_macro_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  output_dir: runs
  timezone: Asia/Shanghai
market:
  enabled: false
text:
  enabled: false
macro_calendar:
  enabled: true
  source: federal_reserve_fomc
  data_classes:
    - central_bank_event
  regions:
    - US
  lookback_days: 1
  lookahead_days: 1
report:
  title: Daily Market Brief
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return config_path
