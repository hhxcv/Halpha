from __future__ import annotations

from typing import Any

from halpha.utils.value_helpers import as_list as _list


FEATURE_FACTOR_CHECK_NAMES = {
    "feature_snapshots",
    "factor_states",
    "multi_source_signals",
    "factor_signal_material",
}
FUSION_CHECK_NAMES = {
    "intelligence_fusion",
    "intelligence_fusion_material",
}
PERSONALIZED_RISK_CHECK_NAMES = {
    "user_state_context",
    "personalized_risk_constraints",
    "personalized_risk_material",
}
POST_DATA_QUALITY_CHECK_NAMES = {
    *FEATURE_FACTOR_CHECK_NAMES,
    *FUSION_CHECK_NAMES,
    *PERSONALIZED_RISK_CHECK_NAMES,
}
QUALITY_STATUS_COUNTS = {"ok": 0, "warning": 0, "degraded": 0, "skipped": 0, "failed": 0}


def named_quality_check_counts(quality: dict[str, Any], names: set[str]) -> dict[str, int]:
    counts = dict(QUALITY_STATUS_COUNTS)
    for check in _list(quality.get("checks")):
        if not isinstance(check, dict) or check.get("name") not in names:
            continue
        status = str(check.get("status") or "unknown")
        if status in counts:
            counts[status] += 1
    return counts
