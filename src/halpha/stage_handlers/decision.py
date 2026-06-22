from __future__ import annotations

from halpha.runtime.pipeline_contracts import StageHandler
from halpha.stage_handlers._lazy import lazy_stage_handler


def stage_handlers() -> dict[str, StageHandler]:
    return {
        "build_market_regime_assessment": lazy_stage_handler(
            "halpha.decision.decision_intelligence",
            "build_market_regime_assessment",
        ),
        "build_risk_assessment": lazy_stage_handler(
            "halpha.decision.decision_intelligence",
            "build_risk_assessment",
        ),
        "build_decision_recommendations": lazy_stage_handler(
            "halpha.decision.decision_intelligence",
            "build_decision_recommendations",
        ),
        "build_watch_triggers": lazy_stage_handler(
            "halpha.decision.decision_intelligence",
            "build_watch_triggers",
        ),
        "build_event_market_confluence": lazy_stage_handler(
            "halpha.decision.event_market_confluence",
            "build_event_market_confluence",
        ),
        "build_event_intelligence_assessment": lazy_stage_handler(
            "halpha.decision.event_intelligence_assessment",
            "build_event_intelligence_assessment",
        ),
        "build_alert_decisions": lazy_stage_handler("halpha.decision.alert_decisions", "build_alert_decisions"),
        "build_alert_decision_material": lazy_stage_handler(
            "halpha.analysis.alert_decision_material",
            "build_alert_decision_material",
        ),
        "build_event_intelligence_material": lazy_stage_handler(
            "halpha.analysis.event_intelligence_material",
            "build_event_intelligence_material",
        ),
        "build_decision_intelligence_delta": lazy_stage_handler(
            "halpha.decision.decision_intelligence",
            "build_decision_intelligence_delta",
        ),
        "build_decision_intelligence_material": lazy_stage_handler(
            "halpha.decision.decision_intelligence",
            "build_decision_intelligence_material",
        ),
        "build_feature_snapshots": lazy_stage_handler("halpha.decision.feature_snapshots", "build_feature_snapshots"),
        "build_factor_states": lazy_stage_handler("halpha.decision.factor_states", "build_factor_states"),
        "build_multi_source_signals": lazy_stage_handler(
            "halpha.decision.multi_source_signals",
            "build_multi_source_signals",
        ),
        "build_intelligence_fusion": lazy_stage_handler(
            "halpha.decision.intelligence_fusion",
            "build_intelligence_fusion",
        ),
        "integrate_intelligence_fusion": lazy_stage_handler(
            "halpha.decision.fusion_integration",
            "integrate_intelligence_fusion",
        ),
        "build_user_state_context": lazy_stage_handler("halpha.decision.user_state", "build_user_state_context"),
        "build_personalized_risk_constraints": lazy_stage_handler(
            "halpha.decision.personalized_risk",
            "build_personalized_risk_constraints",
        ),
        "integrate_personalized_risk_constraints": lazy_stage_handler(
            "halpha.decision.personalized_integration",
            "integrate_personalized_risk_constraints",
        ),
        "build_personalized_risk_material": lazy_stage_handler(
            "halpha.analysis.personalized_risk_material",
            "build_personalized_risk_material",
        ),
    }
