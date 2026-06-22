from __future__ import annotations

from datetime import datetime
from typing import Any

from halpha.decision.decision_artifact_builders import build_decision_recommendations_artifact
from halpha.runtime.pipeline_contracts import RunContext


def build_decision_recommendations(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    return build_decision_recommendations_artifact(config, run, now=now)
