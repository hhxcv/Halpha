from __future__ import annotations

from halpha.data.collection_coverage import build_collection_coverage_state
from halpha.data.collection_planner import plan_collection_from_coverage


REQUESTED_START = "2026-06-01T00:00:00Z"
REQUESTED_END = "2026-06-08T00:00:00Z"


def test_complete_coverage_produces_no_work_plan() -> None:
    state = build_collection_coverage_state(
        [_record(REQUESTED_START, REQUESTED_END, status="collected", records=168)],
        now="2026-06-08T00:00:00Z",
    )

    plan = _plan(state)

    assert plan["status"] == "ok"
    assert plan["strategy"] == "no_work"
    assert plan["gap_ranges"] == []
    assert plan["retry_ranges"] == []
    assert plan["planned_fetch_windows"] == []
    assert plan["skipped_ranges"] == [
        {
            "range_start": REQUESTED_START,
            "range_end": REQUESTED_END,
            "status": "collected",
            "source_artifacts": ["raw/market_data_views.json"],
            "warnings": [],
            "errors": [],
        }
    ]


def test_middle_gap_produces_gap_only_window() -> None:
    state = build_collection_coverage_state(
        [
            _record("2026-06-01T00:00:00Z", "2026-06-03T00:00:00Z", status="collected"),
            _record("2026-06-04T00:00:00Z", "2026-06-08T00:00:00Z", status="collected"),
        ],
        now="2026-06-08T00:00:00Z",
    )

    plan = _plan(state)

    assert plan["strategy"] == "gap_only"
    assert plan["gap_ranges"] == [
        {
            "range_start": "2026-06-03T00:00:00Z",
            "range_end": "2026-06-04T00:00:00Z",
            "status": "unknown",
        }
    ]
    assert plan["planned_fetch_windows"] == [
        {
            "range_start": "2026-06-03T00:00:00Z",
            "range_end": "2026-06-04T00:00:00Z",
            "reason": "missing_coverage",
        }
    ]


def test_partial_and_failed_ranges_are_retried_with_reasons() -> None:
    state = build_collection_coverage_state(
        [
            _record("2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z", status="partial", warnings=["feed lagged"]),
            _record("2026-06-02T00:00:00Z", "2026-06-04T00:00:00Z", status="collected"),
            _record(
                "2026-06-04T00:00:00Z",
                "2026-06-05T00:00:00Z",
                status="failed",
                errors=[{"message": "source timeout"}],
            ),
            _record("2026-06-05T00:00:00Z", "2026-06-08T00:00:00Z", status="collected"),
        ],
        now="2026-06-08T00:00:00Z",
    )

    plan = _plan(state)

    assert plan["strategy"] == "gap_only"
    assert plan["gap_ranges"] == []
    assert plan["retry_ranges"] == [
        {
            "range_start": "2026-06-01T00:00:00Z",
            "range_end": "2026-06-02T00:00:00Z",
            "status": "partial",
            "reason": "partial_coverage",
            "source_artifacts": ["raw/market_data_views.json"],
            "warnings": ["feed lagged"],
            "errors": [],
        },
        {
            "range_start": "2026-06-04T00:00:00Z",
            "range_end": "2026-06-05T00:00:00Z",
            "status": "failed",
            "reason": "failed_coverage",
            "source_artifacts": ["raw/market_data_views.json"],
            "warnings": [],
            "errors": [{"message": "source timeout"}],
        },
    ]
    assert plan["planned_fetch_windows"] == [
        {
            "range_start": "2026-06-01T00:00:00Z",
            "range_end": "2026-06-02T00:00:00Z",
            "reason": "partial_coverage",
        },
        {
            "range_start": "2026-06-04T00:00:00Z",
            "range_end": "2026-06-05T00:00:00Z",
            "reason": "failed_coverage",
        },
    ]


def test_fragmented_gaps_merge_when_threshold_allows() -> None:
    state = build_collection_coverage_state(
        [
            _record("2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z", status="collected"),
            _record("2026-06-03T00:00:00Z", "2026-06-04T00:00:00Z", status="collected"),
            _record("2026-06-05T00:00:00Z", "2026-06-06T00:00:00Z", status="collected"),
            _record("2026-06-07T00:00:00Z", "2026-06-08T00:00:00Z", status="collected"),
        ],
        now="2026-06-08T00:00:00Z",
    )

    plan = _plan(state, merge_gap_threshold_seconds=86_400, max_exact_windows=10)

    assert plan["strategy"] == "merged_gaps"
    assert len(plan["gap_ranges"]) == 3
    assert plan["planned_fetch_windows"] == [
        {
            "range_start": "2026-06-02T00:00:00Z",
            "range_end": "2026-06-07T00:00:00Z",
            "reason": "merged_gaps_more_efficient",
        }
    ]


def test_fragmented_gaps_fall_back_to_full_range_when_exact_fetches_are_inefficient() -> None:
    state = build_collection_coverage_state(
        [
            _record("2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z", status="not_collected"),
            _record("2026-06-02T00:00:00Z", "2026-06-03T00:00:00Z", status="collected"),
            _record("2026-06-03T00:00:00Z", "2026-06-04T00:00:00Z", status="not_collected"),
            _record("2026-06-04T00:00:00Z", "2026-06-05T00:00:00Z", status="collected"),
            _record("2026-06-05T00:00:00Z", "2026-06-06T00:00:00Z", status="not_collected"),
            _record("2026-06-06T00:00:00Z", "2026-06-08T00:00:00Z", status="collected"),
        ],
        now="2026-06-08T00:00:00Z",
    )

    plan = _plan(state, max_exact_windows=2)

    assert plan["status"] == "warning"
    assert plan["strategy"] == "full_range"
    assert plan["planned_fetch_windows"] == [
        {
            "range_start": REQUESTED_START,
            "range_end": REQUESTED_END,
            "reason": "full_range_more_efficient",
        }
    ]
    assert plan["warnings"] == ["fragmented collection gaps exceed max exact windows; planning full requested range."]


def test_unsupported_historical_collection_blocks_plan_without_fake_windows() -> None:
    state = build_collection_coverage_state(
        [_record("2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z", status="collected")],
        now="2026-06-08T00:00:00Z",
    )

    plan = _plan(state, supports_historical=False)

    assert plan["status"] == "blocked"
    assert plan["strategy"] == "blocked"
    assert plan["planned_fetch_windows"] == []
    assert plan["errors"] == [
        {
            "message": "source does not support historical collection for the requested range.",
            "requested_start": REQUESTED_START,
            "requested_end": REQUESTED_END,
        }
    ]


def test_min_fetch_window_widens_small_gap_within_requested_range() -> None:
    state = build_collection_coverage_state(
        [
            _record("2026-06-01T00:00:00Z", "2026-06-03T00:00:00Z", status="collected"),
            _record("2026-06-03T06:00:00Z", "2026-06-08T00:00:00Z", status="collected"),
        ],
        now="2026-06-08T00:00:00Z",
    )

    plan = _plan(state, min_fetch_window_seconds=86_400)

    assert plan["strategy"] == "widened_window"
    assert plan["gap_ranges"] == [
        {
            "range_start": "2026-06-03T00:00:00Z",
            "range_end": "2026-06-03T06:00:00Z",
            "status": "unknown",
        }
    ]
    assert plan["planned_fetch_windows"] == [
        {
            "range_start": "2026-06-02T15:00:00Z",
            "range_end": "2026-06-03T15:00:00Z",
            "reason": "widened_window_more_efficient",
        }
    ]


def test_plan_output_is_deterministically_sorted() -> None:
    state = build_collection_coverage_state(
        [
            _record("2026-06-06T00:00:00Z", "2026-06-08T00:00:00Z", status="collected"),
            _record("2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z", status="collected"),
            _record("2026-06-03T00:00:00Z", "2026-06-04T00:00:00Z", status="collected"),
            _record("2026-06-04T00:00:00Z", "2026-06-05T00:00:00Z", status="failed"),
            _record("2026-06-05T00:00:00Z", "2026-06-06T00:00:00Z", status="collected"),
        ],
        now="2026-06-08T00:00:00Z",
    )

    first = _plan(state)
    second = _plan(state)

    assert first == second
    assert [window["range_start"] for window in first["planned_fetch_windows"]] == [
        "2026-06-02T00:00:00Z",
        "2026-06-04T00:00:00Z",
    ]


def _plan(
    state: dict[str, object],
    *,
    supports_historical: bool = True,
    max_exact_windows: int = 3,
    merge_gap_threshold_seconds: int = 0,
    min_fetch_window_seconds: int = 0,
) -> dict[str, object]:
    return plan_collection_from_coverage(
        state,
        data_type="ohlcv",
        source="binance",
        identity={"symbol": "BTCUSDT", "timeframe": "1h"},
        requested_start=REQUESTED_START,
        requested_end=REQUESTED_END,
        supports_historical=supports_historical,
        now="2026-06-08T00:00:00Z",
        max_exact_windows=max_exact_windows,
        merge_gap_threshold_seconds=merge_gap_threshold_seconds,
        min_fetch_window_seconds=min_fetch_window_seconds,
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
