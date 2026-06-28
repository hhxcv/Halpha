from __future__ import annotations

import json
from pathlib import Path

import pytest

from halpha.data.collection_coverage import (
    COVERAGE_STATE_ARTIFACT,
    build_collection_coverage_state,
    merge_collection_coverage_records,
    summarize_collection_coverage,
    write_collection_coverage_state,
)


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_collection_coverage_records_status_counts_and_summaries(tmp_path: Path) -> None:
    state = write_collection_coverage_state(
        tmp_path / "config.yaml",
        [
            _record("2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z", status="collected", records=24),
            _record("2026-06-02T00:00:00Z", "2026-06-03T00:00:00Z", status="no_data"),
            _record("2026-06-04T00:00:00Z", "2026-06-05T00:00:00Z", status="not_collected"),
        ],
        now="2026-06-05T00:00:00Z",
        source_artifacts=["raw/market_data_views.json"],
    )

    path = tmp_path / COVERAGE_STATE_ARTIFACT
    written = json.loads(path.read_text(encoding="utf-8"))
    summary = summarize_collection_coverage(
        state,
        data_type="ohlcv",
        source="binance",
        identity={"symbol": "BTCUSDT", "timeframe": "1h"},
        requested_start="2026-06-01T00:00:00Z",
        requested_end="2026-06-05T00:00:00Z",
    )

    assert written["status"] == "ok"
    assert written["counts"]["statuses"] == {"collected": 1, "no_data": 1, "not_collected": 1}
    assert written["source_artifacts"] == ["raw/market_data_views.json"]
    assert summary["status_counts"] == {"collected": 1, "no_data": 1, "not_collected": 1}
    assert summary["range_start"] == "2026-06-01T00:00:00Z"
    assert summary["range_end"] == "2026-06-05T00:00:00Z"
    assert summary["not_collected_ranges"] == [
        {"range_start": "2026-06-04T00:00:00Z", "range_end": "2026-06-05T00:00:00Z"}
    ]
    assert summary["unknown_ranges"] == [
        {"range_start": "2026-06-03T00:00:00Z", "range_end": "2026-06-04T00:00:00Z"}
    ]


def test_collection_coverage_merges_adjacent_compatible_intervals() -> None:
    merged = merge_collection_coverage_records(
        [
            _record("2026-06-02T00:00:00Z", "2026-06-03T00:00:00Z", status="collected", records=2),
            _record("2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z", status="collected", records=1),
        ]
    )

    assert len(merged) == 1
    assert merged[0]["range_start"] == "2026-06-01T00:00:00Z"
    assert merged[0]["range_end"] == "2026-06-03T00:00:00Z"
    assert merged[0]["record_count"] == 3
    assert merged[0]["attempt_count"] == 2


def test_collection_coverage_resolved_exact_range_supersedes_partial_attempt() -> None:
    state = build_collection_coverage_state(
        [
            _record(
                "2026-06-01T00:00:00Z",
                "2026-06-02T00:00:00Z",
                status="partial",
                records=23,
                warnings=["feed lagged"],
            ),
            _record("2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z", status="collected", records=24),
        ],
        now="2026-06-03T00:00:00Z",
    )

    assert state["status"] == "ok"
    assert state["counts"]["statuses"] == {"collected": 1}
    assert state["records"][0]["status"] == "collected"
    assert state["records"][0]["record_count"] == 24
    assert state["records"][0]["attempt_count"] == 2
    assert state["records"][0]["warnings"] == []


def test_collection_coverage_exact_duplicate_uses_latest_count_without_double_counting() -> None:
    merged = merge_collection_coverage_records(
        [
            _record("2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z", status="collected", records=23),
            {
                **_record("2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z", status="collected", records=24),
                "updated_at": "2026-06-03T00:00:00Z",
                "latest_attempt_at": "2026-06-03T00:00:00Z",
                "latest_success_at": "2026-06-03T00:00:00Z",
            },
        ]
    )

    assert len(merged) == 1
    assert merged[0]["status"] == "collected"
    assert merged[0]["record_count"] == 24
    assert merged[0]["attempt_count"] == 2


def test_collection_coverage_preserves_partial_and_failed_intervals() -> None:
    state = build_collection_coverage_state(
        [
            _record("2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z", status="partial", warnings=["feed lagged"]),
            _record("2026-06-02T00:00:00Z", "2026-06-03T00:00:00Z", status="partial", warnings=["feed lagged"]),
            _record(
                "2026-06-03T00:00:00Z",
                "2026-06-04T00:00:00Z",
                status="failed",
                errors=[{"message": "source timeout"}],
            ),
        ],
        now="2026-06-05T00:00:00Z",
    )
    summary = summarize_collection_coverage(state, data_type="ohlcv")

    assert state["status"] == "failed"
    assert state["counts"]["statuses"] == {"failed": 1, "partial": 2}
    assert summary["partial_ranges"] == [
        {"range_start": "2026-06-01T00:00:00Z", "range_end": "2026-06-02T00:00:00Z"},
        {"range_start": "2026-06-02T00:00:00Z", "range_end": "2026-06-03T00:00:00Z"},
    ]
    assert summary["failed_ranges"] == [
        {"range_start": "2026-06-03T00:00:00Z", "range_end": "2026-06-04T00:00:00Z"}
    ]


def test_collection_coverage_rejects_unknown_status() -> None:
    with pytest.raises(ValueError, match="unsupported collection coverage status"):
        merge_collection_coverage_records(
            [_record("2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z", status="complete")]
        )


def _record(
    start: str,
    end: str,
    *,
    status: str,
    records: int = 0,
    warnings: list[str] | None = None,
    errors: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "data_type": "ohlcv",
        "source": "binance",
        "identity": {"symbol": "BTCUSDT", "timeframe": "1h"},
        "range_start": start,
        "range_end": end,
        "status": status,
        "record_count": records,
        "attempt_count": 1,
        "latest_attempt_at": end,
        "latest_success_at": end if status in {"collected", "no_data"} else None,
        "updated_at": end,
        "coverage_method": "explicit",
        "source_artifacts": ["raw/market_data_views.json"],
        "warnings": warnings or [],
        "errors": errors or [],
    }
