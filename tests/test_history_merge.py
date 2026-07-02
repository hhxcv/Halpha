from __future__ import annotations

from typing import Any

from halpha.data.history_merge import merge_history_records


def test_merge_history_records_inserts_and_merges_duplicate_metadata() -> None:
    existing = [
        {
            "history_key": "b",
            "payload_signature": "old",
            "origin_run_ids": ["run-1"],
            "last_seen_run_id": "run-1",
            "last_seen_at": "2026-06-20T00:00:00Z",
            "source_artifacts": ["raw/one.json"],
            "affected_assets": ["BTC"],
            "warnings": [],
            "errors": [],
            "status": "active",
        }
    ]
    incoming = [
        {
            "history_key": "b",
            "payload_signature": "new",
            "origin_run_ids": ["run-2"],
            "last_seen_run_id": "run-2",
            "last_seen_at": "2026-06-20T01:00:00Z",
            "source_artifacts": ["raw/two.json"],
            "affected_assets": ["ETH", "BTC"],
            "warnings": ["incoming warning"],
            "errors": [{"message": "incoming error"}],
            "status": "warning",
        },
        {
            "history_key": "a",
            "payload_signature": "same",
            "origin_run_ids": ["run-2"],
            "last_seen_run_id": "run-2",
            "last_seen_at": "2026-06-20T01:00:00Z",
            "source_artifacts": ["raw/two.json"],
            "warnings": [],
            "errors": [],
            "status": "active",
        },
    ]

    records, summary = merge_history_records(
        existing,
        incoming,
        conflict_label="macro calendar",
        sort_key=_sort_key,
        extra_string_list_fields=("affected_assets",),
    )

    assert [record["history_key"] for record in records] == ["a", "b"]
    merged = records[1]
    assert merged["origin_run_ids"] == ["run-1", "run-2"]
    assert merged["last_seen_run_id"] == "run-2"
    assert merged["last_seen_at"] == "2026-06-20T01:00:00Z"
    assert merged["source_artifacts"] == ["raw/one.json", "raw/two.json"]
    assert merged["affected_assets"] == ["BTC", "ETH"]
    assert merged["warnings"] == [
        "conflicting duplicate macro calendar record: b",
        "incoming warning",
    ]
    assert merged["errors"] == [{"message": "incoming error"}]
    assert merged["status"] == "warning"
    assert summary == {
        "inserted_records": 1,
        "updated_records": 1,
        "duplicate_records": 1,
        "conflicting_duplicates": 1,
        "warnings": ["conflicting duplicate macro calendar record: b"],
    }


def test_merge_history_records_can_replace_resolved_duplicate_payload() -> None:
    existing = [
        {
            "history_key": "fomc",
            "payload_signature": "old",
            "origin_run_ids": ["run-1"],
            "first_seen_run_id": "run-1",
            "last_seen_run_id": "run-1",
            "first_seen_at": "2026-06-20T00:00:00Z",
            "last_seen_at": "2026-06-20T00:00:00Z",
            "source_artifacts": ["raw/one.json"],
            "affected_assets": ["BTC"],
            "warnings": ["conflicting duplicate macro calendar record: fomc"],
            "errors": [{"message": "old parse warning"}],
            "status": "warning",
            "raw_fields": {"summary_of_economic_projections": False},
        }
    ]
    incoming = [
        {
            "history_key": "fomc",
            "payload_signature": "new",
            "origin_run_ids": ["run-2"],
            "first_seen_run_id": "run-2",
            "last_seen_run_id": "run-2",
            "first_seen_at": "2026-06-20T01:00:00Z",
            "last_seen_at": "2026-06-20T01:00:00Z",
            "source_artifacts": ["raw/two.json"],
            "affected_assets": ["ETH"],
            "warnings": [],
            "errors": [],
            "status": "active",
            "raw_fields": {"summary_of_economic_projections": True},
        }
    ]

    records, summary = merge_history_records(
        existing,
        incoming,
        conflict_label="macro calendar",
        sort_key=_sort_key,
        extra_string_list_fields=("affected_assets",),
        replace_conflicting_payload=True,
    )

    assert len(records) == 1
    assert records[0]["raw_fields"] == {"summary_of_economic_projections": True}
    assert records[0]["warnings"] == []
    assert records[0]["errors"] == []
    assert records[0]["status"] == "active"
    assert records[0]["affected_assets"] == ["BTC", "ETH"]
    assert records[0]["origin_run_ids"] == ["run-1", "run-2"]
    assert records[0]["first_seen_run_id"] == "run-1"
    assert records[0]["last_seen_run_id"] == "run-2"
    assert records[0]["source_artifacts"] == ["raw/one.json", "raw/two.json"]
    assert summary == {
        "inserted_records": 0,
        "updated_records": 1,
        "duplicate_records": 1,
        "conflicting_duplicates": 0,
        "warnings": [],
    }


def _sort_key(record: dict[str, Any]) -> tuple[str]:
    return (str(record["history_key"]),)
