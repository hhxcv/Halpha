from __future__ import annotations

from datetime import datetime
from typing import Any

from halpha.decision.decision_intelligence import build_watch_triggers_artifact
from halpha.runtime.pipeline_contracts import RunContext


def build_watch_triggers(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    return build_watch_triggers_artifact(config, run, now=now)
