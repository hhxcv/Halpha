from __future__ import annotations

from datetime import datetime
from typing import Any

from halpha.decision.decision_intelligence import (
    build_decision_intelligence_delta as _build_decision_intelligence_delta,
)
from halpha.runtime.pipeline_contracts import RunContext


def build_decision_intelligence_delta(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    return _build_decision_intelligence_delta(config, run, now=now)
