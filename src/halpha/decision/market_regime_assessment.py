from __future__ import annotations

from datetime import datetime
from typing import Any

from halpha.decision.decision_artifact_builders import build_market_regime_assessment_artifact
from halpha.runtime.pipeline_contracts import RunContext


def build_market_regime_assessment(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    return build_market_regime_assessment_artifact(config, run, now=now)
