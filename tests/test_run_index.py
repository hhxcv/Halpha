from __future__ import annotations

from contextlib import closing
import json
import sqlite3
from pathlib import Path
from typing import Any

from halpha.config import load_config
from halpha.pipeline import PipelineError, run_pipeline, run_pipeline_stage
from halpha.product.product_validation_inspection import inspect_product_validation
from halpha.data.run_index import write_run_index


def test_run_index_records_successful_run_metadata(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="collect_market_data",
        stage_handlers={"collect_market_data": _market_stage},
    )

    assert result.succeeded is True
    index_path = tmp_path / "data" / "research" / "index.sqlite"
    manifest = _manifest(result.run.manifest_path)
    assert index_path.is_file()
    assert manifest["artifacts"]["run_index"] == "data/research/index.sqlite"
    assert manifest["run_index"]["status"] == "ok"

    with closing(sqlite3.connect(index_path)) as connection:
        run_row = connection.execute(
            """
            SELECT run_id, run_dir, config_path, status, codex_status, manifest_path
            FROM runs
            WHERE run_id = ?
            """,
            (result.run.run_id,),
        ).fetchone()
        latest = dict(connection.execute("SELECT key, run_id FROM run_latest").fetchall())
        artifacts = connection.execute(
            "SELECT artifact_key, path, kind FROM run_artifacts WHERE run_id = ? ORDER BY artifact_key",
            (result.run.run_id,),
        ).fetchall()

    assert run_row == (
        result.run.run_id,
        f"runs/{result.run.run_id}",
        "config.yaml",
        "succeeded",
        "not_run",
        f"runs/{result.run.run_id}/run_manifest.json",
    )
    assert latest["latest_run"] == result.run.run_id
    assert latest["latest_successful_run"] == result.run.run_id
    assert ("market", "raw/market.json", "raw") in artifacts
    assert ("run_index", "data/research/index.sqlite", "shared_data") in artifacts


def test_run_index_records_failed_runs(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={"collect_market_data": _failed_stage},
    )

    assert result.succeeded is False
    with closing(sqlite3.connect(tmp_path / "data" / "research" / "index.sqlite")) as connection:
        row = connection.execute(
            "SELECT status, failed_stage, error_count FROM runs WHERE run_id = ?",
            (result.run.run_id,),
        ).fetchone()
        latest = dict(connection.execute("SELECT key, run_id FROM run_latest").fetchall())

    assert row == ("failed", "collect_market_data", 1)
    assert latest["latest_run"] == result.run.run_id
    assert "latest_successful_run" not in latest


def test_run_index_reindexes_single_stage_rerun_without_duplicate_rows(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    initial = run_pipeline(
        config,
        config_path=config_path,
        until_stage="collect_market_data",
        stage_handlers={"collect_market_data": _market_stage},
    )

    result = run_pipeline_stage(
        config,
        config_path=config_path,
        run_dir=initial.run.run_dir,
        stage="collect_text_events",
        stage_handlers={"collect_text_events": _text_stage},
    )

    assert result.succeeded is True
    manifest = _manifest(result.run.manifest_path)
    with closing(sqlite3.connect(tmp_path / "data" / "research" / "index.sqlite")) as connection:
        stage_count = connection.execute(
            "SELECT COUNT(*) FROM run_stages WHERE run_id = ?",
            (result.run.run_id,),
        ).fetchone()[0]
        text_artifact = connection.execute(
            """
            SELECT kind FROM run_artifacts
            WHERE run_id = ? AND artifact_key = ? AND path = ?
            """,
            (result.run.run_id, "text_events", "raw/text_events.json"),
        ).fetchone()

    assert stage_count == len(manifest["stages"])
    assert text_artifact == ("raw",)

    write_run_index(result.run, now="2026-06-05T00:00:00Z")
    with closing(sqlite3.connect(tmp_path / "data" / "research" / "index.sqlite")) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM run_stages WHERE run_id = ?",
                (result.run.run_id,),
            ).fetchone()[0]
            == len(manifest["stages"])
        )


def test_run_index_releases_sqlite_file_after_write_and_read_access(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="collect_market_data",
        stage_handlers={"collect_market_data": _market_stage},
    )

    assert result.succeeded is True
    validation = inspect_product_validation(config, config_path=config_path)
    assert validation.status == "ok"
    index_path = tmp_path / "data" / "research" / "index.sqlite"
    moved_path = index_path.with_name("index-moved.sqlite")

    index_path.rename(moved_path)
    assert moved_path.is_file()
    moved_path.unlink()
    assert not moved_path.exists()


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
run:
  output_dir: runs
  timezone: Asia/Shanghai
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
text:
  enabled: true
  max_items: 1
  sources:
    - name: coindesk
      type: rss
      url: https://www.coindesk.com/arc/outboundfeeds/rss/
report:
  title: Daily Market Brief
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return path


def _manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _market_stage(config, run) -> list[str]:
    artifact = run.raw_dir / "market.json"
    artifact.write_text("{}", encoding="utf-8")
    run.manifest["artifacts"]["market"] = "raw/market.json"
    return ["raw/market.json"]


def _text_stage(config, run) -> list[str]:
    artifact = run.raw_dir / "text_events.json"
    artifact.write_text("{}", encoding="utf-8")
    run.manifest["artifacts"]["text_events"] = "raw/text_events.json"
    return ["raw/text_events.json"]


def _failed_stage(config, run) -> None:
    raise PipelineError("collection failed", stage="collect_market_data", exit_code=3)
