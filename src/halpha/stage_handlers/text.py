from __future__ import annotations

from halpha.runtime.pipeline_contracts import StageHandler
from halpha.stage_handlers._lazy import lazy_stage_handler


def stage_handlers() -> dict[str, StageHandler]:
    return {
        "collect_text_events": lazy_stage_handler("halpha.collectors.text", "collect_text_events"),
        "build_text_event_records": lazy_stage_handler("halpha.text.text_event_records", "build_text_event_records"),
        "build_text_entity_evidence": lazy_stage_handler(
            "halpha.text.text_entity_evidence",
            "build_text_entity_evidence",
        ),
        "build_text_event_classification_evidence": lazy_stage_handler(
            "halpha.text.text_event_classification",
            "build_text_event_classification_evidence",
        ),
        "build_text_event_topics": lazy_stage_handler("halpha.text.text_event_topics", "build_text_event_topics"),
        "build_text_event_signals": lazy_stage_handler(
            "halpha.text.text_event_signals",
            "build_text_event_signals",
        ),
    }
