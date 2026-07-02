from __future__ import annotations

from typing import Any, Callable


def merge_history_records(
    existing_records: list[dict[str, Any]],
    incoming_records: list[dict[str, Any]],
    *,
    conflict_label: str,
    sort_key: Callable[[dict[str, Any]], tuple[Any, ...]],
    extra_string_list_fields: tuple[str, ...] = (),
    replace_conflicting_payload: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_key = {record["history_key"]: record for record in existing_records}
    inserted = 0
    updated = 0
    duplicate = 0
    conflicts = 0
    warnings: list[str] = []

    for incoming in incoming_records:
        existing = by_key.get(incoming["history_key"])
        if existing is None:
            by_key[incoming["history_key"]] = incoming
            inserted += 1
            continue

        duplicate += 1
        updated += 1
        if existing.get("payload_signature") != incoming.get("payload_signature"):
            if replace_conflicting_payload:
                by_key[incoming["history_key"]] = _replace_with_latest_payload(
                    existing,
                    incoming,
                    conflict_label=conflict_label,
                    extra_string_list_fields=extra_string_list_fields,
                )
                continue
            conflicts += 1
            warning = f"conflicting duplicate {conflict_label} record: {incoming['history_key']}"
            warnings.append(warning)
            existing["warnings"] = _unique_sorted([*existing.get("warnings", []), warning])
            existing["status"] = "warning"
        for field in extra_string_list_fields:
            existing[field] = _unique_sorted([*existing.get(field, []), *incoming.get(field, [])])
        existing["origin_run_ids"] = _unique_sorted(
            [*existing.get("origin_run_ids", []), *incoming.get("origin_run_ids", [])]
        )
        existing["last_seen_run_id"] = incoming["last_seen_run_id"]
        existing["last_seen_at"] = _latest_timestamp(existing.get("last_seen_at"), incoming.get("last_seen_at"))
        existing["source_artifacts"] = _unique_sorted(
            [*existing.get("source_artifacts", []), *incoming.get("source_artifacts", [])]
        )
        existing["warnings"] = _unique_sorted([*existing.get("warnings", []), *incoming.get("warnings", [])])
        existing["errors"] = _error_list([*existing.get("errors", []), *incoming.get("errors", [])])
        if (existing["warnings"] or existing["errors"]) and existing.get("status") == "active":
            existing["status"] = "warning"

    return (
        sorted(by_key.values(), key=sort_key),
        {
            "inserted_records": inserted,
            "updated_records": updated,
            "duplicate_records": duplicate,
            "conflicting_duplicates": conflicts,
            "warnings": _unique_sorted(warnings),
        },
    )


def _replace_with_latest_payload(
    existing: dict[str, Any],
    incoming: dict[str, Any],
    *,
    conflict_label: str,
    extra_string_list_fields: tuple[str, ...],
) -> dict[str, Any]:
    merged = dict(incoming)
    for field in extra_string_list_fields:
        merged[field] = _unique_sorted([*existing.get(field, []), *incoming.get(field, [])])
    merged["origin_run_ids"] = _unique_sorted([*existing.get("origin_run_ids", []), *incoming.get("origin_run_ids", [])])
    merged["first_seen_run_id"] = existing.get("first_seen_run_id") or incoming.get("first_seen_run_id")
    merged["first_seen_at"] = _earliest_timestamp(existing.get("first_seen_at"), incoming.get("first_seen_at"))
    merged["last_seen_run_id"] = incoming.get("last_seen_run_id") or existing.get("last_seen_run_id")
    merged["last_seen_at"] = _latest_timestamp(existing.get("last_seen_at"), incoming.get("last_seen_at"))
    merged["source_artifacts"] = _unique_sorted(
        [*existing.get("source_artifacts", []), *incoming.get("source_artifacts", [])]
    )
    merged["warnings"] = _without_conflict_warnings(incoming.get("warnings", []), conflict_label=conflict_label)
    merged["errors"] = _error_list(incoming.get("errors", []))
    if (merged["warnings"] or merged["errors"]) and merged.get("status") == "active":
        merged["status"] = "warning"
    return merged


def _error_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _earliest_timestamp(left: Any, right: Any) -> str:
    values = [str(value) for value in (left, right) if value]
    return min(values) if values else ""


def _latest_timestamp(left: Any, right: Any) -> str:
    left_value = str(left) if left else ""
    right_value = str(right) if right else ""
    return max(left_value, right_value)


def _without_conflict_warnings(value: Any, *, conflict_label: str) -> list[str]:
    prefix = f"conflicting duplicate {conflict_label} record:"
    return _unique_sorted([item for item in value or [] if isinstance(item, str) and not item.startswith(prefix)])


def _unique_sorted(values: list[Any]) -> list[str]:
    return sorted({str(value) for value in values if value})
