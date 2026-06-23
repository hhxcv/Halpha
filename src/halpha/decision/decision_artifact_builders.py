from __future__ import annotations

from datetime import datetime
from typing import Any

from halpha.decision.decision_recommendations import build_decision_recommendations
from halpha.decision.market_regime_assessment import build_market_regime_assessment
from halpha.decision.risk_assessment import build_risk_assessment
from halpha.decision.watch_triggers import build_watch_triggers
from halpha.runtime.pipeline_contracts import RunContext


def build_market_regime_assessment_artifact(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    return build_market_regime_assessment(config, run, now=now)


def build_risk_assessment_artifact(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    return build_risk_assessment(config, run, now=now)


def build_decision_recommendations_artifact(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    return build_decision_recommendations(config, run, now=now)


def build_watch_triggers_artifact(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    return build_watch_triggers(config, run, now=now)
