from __future__ import annotations

from datetime import datetime, timedelta, timezone

from halpha.dashboard.time import utc_timestamp
from halpha.utils.value_helpers import as_dict, as_list, strict_int, stringified_list


def test_value_helpers_coerce_common_artifact_values() -> None:
    source_dict = {"status": "available"}
    source_list = ["a", 2, None]

    assert as_dict(source_dict) is source_dict
    assert as_dict(["not", "dict"]) == {}
    assert as_list(source_list) is source_list
    assert as_list({"not": "list"}) == []
    assert stringified_list(source_list) == ["a", "2", "None"]
    assert stringified_list("not-list") == []


def test_strict_int_keeps_only_non_bool_ints() -> None:
    assert strict_int(3) == 3
    assert strict_int(True) == 0
    assert strict_int("3") == 0
    assert strict_int(3.0) == 0


def test_utc_timestamp_formats_aware_and_naive_values_as_utc() -> None:
    east_8 = timezone(timedelta(hours=8))

    assert utc_timestamp(datetime(2026, 6, 20, 8, 30, 45, 123, tzinfo=east_8)) == "2026-06-20T00:30:45Z"
    assert utc_timestamp(datetime(2026, 6, 20, 8, 30, 45, 123)) == "2026-06-20T08:30:45Z"
