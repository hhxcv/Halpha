from __future__ import annotations

from halpha.pipeline_stage_handlers import default_stage_handlers
from halpha.pipeline_stages import STAGE_ORDER, downstream_closure, operation_metadata, validate_stage_graph
from halpha.stage_handlers import DOMAIN_STAGE_HANDLER_FACTORIES, domain_stage_handlers


def test_default_stage_handlers_cover_stage_order_without_fallbacks() -> None:
    handlers = default_stage_handlers()

    assert list(handlers) == list(STAGE_ORDER)
    assert all("_unimplemented_handler" not in handler.__qualname__ for handler in handlers.values())


def test_pipeline_operation_graph_covers_stage_order_and_is_acyclic() -> None:
    validate_stage_graph()

    metadata = operation_metadata()
    assert [operation["operation_id"] for operation in metadata] == list(STAGE_ORDER)
    assert metadata[0]["dependencies"] == []
    assert metadata[0]["outputs"] == ["raw/market.json"]
    assert metadata[1]["dependencies"] == [STAGE_ORDER[0]]
    assert next(operation for operation in metadata if operation["operation_id"] == "run_codex_report")[
        "enabled_condition"
    ] == "codex.enabled and not --no-codex"


def test_downstream_closure_uses_canonical_order_and_terminal_boundary() -> None:
    assert downstream_closure("build_research_context") == [
        "build_research_context",
        "build_codex_context",
        "run_codex_report",
        "validate_product_contracts",
    ]
    assert downstream_closure("build_research_context", through_stage="build_codex_context") == [
        "build_research_context",
        "build_codex_context",
    ]


def test_domain_stage_handler_registries_are_disjoint_and_complete() -> None:
    seen: dict[str, str] = {}

    for factory, handlers in zip(DOMAIN_STAGE_HANDLER_FACTORIES, domain_stage_handlers(), strict=True):
        assert handlers
        overlap = set(handlers) & set(seen)
        assert not overlap, f"{factory.__module__}.{factory.__name__} duplicates {sorted(overlap)}"
        for stage in handlers:
            seen[stage] = factory.__module__

    assert set(seen) == set(STAGE_ORDER)


def test_default_stage_handlers_apply_overrides_after_domain_groups() -> None:
    def replacement(config, run) -> list[str]:
        return []

    handlers = default_stage_handlers({"collect_market_data": replacement})

    assert handlers["collect_market_data"] is replacement


def test_decision_stage_handlers_use_artifact_modules() -> None:
    handlers = default_stage_handlers()

    assert getattr(handlers["build_market_regime_assessment"], "stage_module") == (
        "halpha.decision.market_regime_assessment"
    )
    assert getattr(handlers["build_risk_assessment"], "stage_module") == "halpha.decision.risk_assessment"
    assert getattr(handlers["build_decision_recommendations"], "stage_module") == (
        "halpha.decision.decision_recommendations"
    )
    assert getattr(handlers["build_watch_triggers"], "stage_module") == "halpha.decision.watch_triggers"
    assert getattr(handlers["build_decision_intelligence_delta"], "stage_module") == (
        "halpha.decision.decision_intelligence_delta_stage"
    )
    assert getattr(handlers["build_decision_intelligence_material"], "stage_module") == (
        "halpha.decision.decision_intelligence_material_stage"
    )
