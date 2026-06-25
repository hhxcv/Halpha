from __future__ import annotations

from typing import Any


def assert_history_traceability(
    record: dict[str, Any],
    *,
    origin_run_ids: list[str],
    first_seen_run_id: str,
    last_seen_run_id: str,
    source_artifacts: list[str],
) -> None:
    assert record["origin_run_ids"] == origin_run_ids
    assert record["first_seen_run_id"] == first_seen_run_id
    assert record["last_seen_run_id"] == last_seen_run_id
    assert record["source_artifacts"] == source_artifacts
