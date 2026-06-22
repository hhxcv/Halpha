from __future__ import annotations

from datetime import datetime
from typing import Any

from halpha.decision.decision_intelligence import (
    _build_decision_recommendations_artifact,
    _build_market_regime_assessment_artifact,
    _build_risk_assessment_artifact,
    _build_watch_triggers_artifact,
)
from halpha.runtime.pipeline_contracts import RunContext


def build_market_regime_assessment_artifact(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    return _build_market_regime_assessment_artifact(config, run, now=now)


def build_risk_assessment_artifact(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    return _build_risk_assessment_artifact(config, run, now=now)


def build_decision_recommendations_artifact(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    return _build_decision_recommendations_artifact(config, run, now=now)


def build_watch_triggers_artifact(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    return _build_watch_triggers_artifact(config, run, now=now)
