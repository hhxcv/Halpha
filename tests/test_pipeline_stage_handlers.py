from __future__ import annotations

import pytest

import halpha.pipeline_stages as pipeline_stages
from halpha.pipeline_stage_handlers import default_stage_handlers
from halpha.pipeline_stages import (
    OPERATION_ORDER,
    STAGE_ORDER,
    STAGE_TASKS,
    downstream_closure,
    operation_downstream_closure,
    operation_metadata,
    tasks_for_stage,
    validate_stage_graph,
)
from halpha.stage_handlers import DOMAIN_STAGE_HANDLER_FACTORIES, domain_stage_handlers


def test_default_stage_handlers_cover_stage_order_without_fallbacks() -> None:
    handlers = default_stage_handlers()

    assert list(handlers) == list(OPERATION_ORDER)
    assert all("_unimplemented_handler" not in handler.__qualname__ for handler in handlers.values())


def test_pipeline_operation_graph_covers_stage_order_and_is_acyclic() -> None:
    validate_stage_graph()

    assert list(STAGE_ORDER) == [
        "refresh_data",
        "build_source_evidence",
        "run_strategy_research",
        "synthesize_intelligence",
        "build_materials",
        "generate_report",
        "finalize_run",
    ]
    assert tasks_for_stage("generate_report") == [
        "build_research_context",
        "build_codex_context",
        "run_codex_report",
    ]
    assert STAGE_TASKS["finalize_run"] == (
        "write_outcome_history",
        "write_research_data_catalog",
        "validate_product_contracts",
    )

    metadata = operation_metadata()
    assert [operation["operation_id"] for operation in metadata] == list(OPERATION_ORDER)
    assert metadata[0]["dependencies"] == []
    assert metadata[0]["outputs"] == ["raw/market.json"]
    assert metadata[1]["dependencies"] == []
    assert next(operation for operation in metadata if operation["operation_id"] == "sync_derivatives_market_history")[
        "dependencies"
    ] == ["collect_derivatives_market_data"]
    assert next(operation for operation in metadata if operation["operation_id"] == "collect_text_events")[
        "dependencies"
    ] == []
    assert next(operation for operation in metadata if operation["operation_id"] == "run_codex_report")[
        "enabled_condition"
    ] == "codex.enabled and not --no-codex"


def test_downstream_closure_uses_canonical_order_and_terminal_boundary() -> None:
    assert downstream_closure("generate_report") == [
        "generate_report",
        "finalize_run",
    ]
    assert downstream_closure("generate_report", through_stage="generate_report") == ["generate_report"]
    assert operation_downstream_closure("build_research_context") == [
        "build_research_context",
        "build_codex_context",
        "run_codex_report",
        "write_outcome_history",
        "write_research_data_catalog",
        "validate_product_contracts",
    ]
    assert operation_downstream_closure("build_research_context", through_operation="build_codex_context") == [
        "build_research_context",
        "build_codex_context",
    ]


def test_operation_downstream_closure_keeps_macro_source_branch_specific() -> None:
    closure = operation_downstream_closure("collect_macro_calendar_data")

    assert "sync_macro_calendar_history" in closure
    assert "build_macro_calendar_views" in closure
    assert "build_macro_calendar_context" in closure
    assert "build_risk_assessment" in closure
    assert "build_intelligence_fusion" in closure
    assert "build_decision_recommendations" in closure
    assert "build_macro_calendar_material" in closure
    assert "build_research_context" in closure
    assert "run_codex_report" in closure
    assert "validate_product_contracts" in closure
    assert "collect_onchain_flow_data" not in closure
    assert "sync_onchain_flow_history" not in closure
    assert "collect_text_events" not in closure
    assert "build_text_event_records" not in closure


def test_operation_downstream_closure_keeps_market_signal_branch_specific() -> None:
    closure = operation_downstream_closure("build_market_signals")

    assert "build_market_regime_assessment" in closure
    assert "build_risk_assessment" in closure
    assert "build_event_market_confluence" in closure
    assert "build_event_intelligence_assessment" in closure
    assert "build_feature_snapshots" in closure
    assert "build_factor_states" in closure
    assert "build_multi_source_signals" in closure
    assert "build_intelligence_fusion" in closure
    assert "build_decision_recommendations" in closure
    assert "build_alert_decisions" in closure
    assert "build_market_signal_material" in closure
    assert "build_research_context" in closure
    assert "validate_product_contracts" in closure
    assert "collect_market_data" not in closure
    assert "sync_ohlcv" not in closure
    assert "collect_text_events" not in closure
    assert "build_market_data_views" not in closure


def test_operation_downstream_closure_keeps_alert_decisions_out_of_fusion_inputs() -> None:
    closure = operation_downstream_closure("build_alert_decisions")

    assert "build_intelligence_fusion" not in closure
    assert "build_outcome_targets" in closure
    assert "evaluate_outcomes" in closure
    assert "build_alert_decision_material" in closure
    assert "build_research_context" in closure
    assert "build_codex_context" in closure
    assert "run_codex_report" in closure
    assert "write_outcome_history" in closure
    assert "write_research_data_catalog" in closure
    assert "validate_product_contracts" in closure


def test_stage_graph_rejects_missing_dependency_declarations(monkeypatch: pytest.MonkeyPatch) -> None:
    dependencies = dict(pipeline_stages.OPERATION_DEPENDENCIES)
    dependencies.pop("collect_text_events")
    monkeypatch.setattr(pipeline_stages, "OPERATION_DEPENDENCIES", dependencies)

    with pytest.raises(ValueError, match="missing dependency declarations"):
        pipeline_stages.validate_stage_graph()


def test_stage_graph_rejects_unknown_dependency_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    dependencies = dict(pipeline_stages.OPERATION_DEPENDENCIES)
    dependencies["build_market_data_views"] = ("missing_task",)
    monkeypatch.setattr(pipeline_stages, "OPERATION_DEPENDENCIES", dependencies)
    monkeypatch.setattr(pipeline_stages, "STAGE_OPERATIONS", _operations_from_dependencies(dependencies))

    with pytest.raises(ValueError, match="depends on unknown operation missing_task"):
        pipeline_stages.validate_stage_graph()


def test_stage_graph_rejects_duplicate_dependency_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    dependencies = dict(pipeline_stages.OPERATION_DEPENDENCIES)
    dependencies["build_risk_assessment"] = ("build_market_signals", "build_market_signals")
    monkeypatch.setattr(pipeline_stages, "OPERATION_DEPENDENCIES", dependencies)
    monkeypatch.setattr(pipeline_stages, "STAGE_OPERATIONS", _operations_from_dependencies(dependencies))

    with pytest.raises(ValueError, match="declares duplicate dependencies"):
        pipeline_stages.validate_stage_graph()


def test_stage_graph_rejects_self_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    dependencies = dict(pipeline_stages.OPERATION_DEPENDENCIES)
    dependencies["build_market_signals"] = ("build_market_signals",)
    monkeypatch.setattr(pipeline_stages, "OPERATION_DEPENDENCIES", dependencies)
    monkeypatch.setattr(pipeline_stages, "STAGE_OPERATIONS", _operations_from_dependencies(dependencies))

    with pytest.raises(ValueError, match="depends on itself"):
        pipeline_stages.validate_stage_graph()


def test_stage_graph_rejects_cycles(monkeypatch: pytest.MonkeyPatch) -> None:
    dependencies = dict(pipeline_stages.OPERATION_DEPENDENCIES)
    dependencies["build_market_signals"] = ("build_risk_assessment",)
    dependencies["build_risk_assessment"] = ("build_market_signals",)
    monkeypatch.setattr(pipeline_stages, "OPERATION_DEPENDENCIES", dependencies)
    monkeypatch.setattr(pipeline_stages, "STAGE_OPERATIONS", _operations_from_dependencies(dependencies))

    with pytest.raises(ValueError, match="contains a cycle"):
        pipeline_stages.validate_stage_graph()


def test_stage_graph_rejects_later_product_stage_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    dependencies = dict(pipeline_stages.OPERATION_DEPENDENCIES)
    dependencies["collect_text_events"] = ("build_market_data_views",)
    monkeypatch.setattr(pipeline_stages, "OPERATION_DEPENDENCIES", dependencies)
    monkeypatch.setattr(pipeline_stages, "STAGE_OPERATIONS", _operations_from_dependencies(dependencies))

    with pytest.raises(ValueError, match="depends on later-stage task build_market_data_views"):
        pipeline_stages.validate_stage_graph()


def test_stage_graph_rejects_duplicate_output_producers(monkeypatch: pytest.MonkeyPatch) -> None:
    outputs = dict(pipeline_stages.STAGE_OUTPUTS)
    outputs["collect_text_events"] = ("raw/market.json",)
    monkeypatch.setattr(pipeline_stages, "STAGE_OUTPUTS", outputs)

    with pytest.raises(ValueError, match="duplicate output"):
        pipeline_stages.validate_stage_graph()


def test_stage_graph_rejects_output_declaration_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    original_outputs = dict(pipeline_stages.STAGE_OUTPUTS)
    outputs = dict(original_outputs)
    outputs.pop("collect_text_events")
    monkeypatch.setattr(pipeline_stages, "STAGE_OUTPUTS", outputs)

    with pytest.raises(ValueError, match="missing output declarations"):
        pipeline_stages.validate_stage_graph()

    outputs = dict(original_outputs)
    outputs["missing_task"] = ("raw/missing.json",)
    monkeypatch.setattr(pipeline_stages, "STAGE_OUTPUTS", outputs)

    with pytest.raises(ValueError, match="unknown output declarations"):
        pipeline_stages.validate_stage_graph()


def test_domain_stage_handler_registries_are_disjoint_and_complete() -> None:
    seen: dict[str, str] = {}

    for factory, handlers in zip(DOMAIN_STAGE_HANDLER_FACTORIES, domain_stage_handlers(), strict=True):
        assert handlers
        overlap = set(handlers) & set(seen)
        assert not overlap, f"{factory.__module__}.{factory.__name__} duplicates {sorted(overlap)}"
        for stage in handlers:
            seen[stage] = factory.__module__

    assert set(seen) == set(OPERATION_ORDER)


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


def _operations_from_dependencies(
    dependencies: dict[str, tuple[str, ...]],
) -> tuple[pipeline_stages.StageOperation, ...]:
    return tuple(
        pipeline_stages.StageOperation(
            operation_id=operation_id,
            dependencies=dependencies.get(operation_id, ()),
            outputs=pipeline_stages.STAGE_OUTPUTS.get(operation_id, ()),
            enabled_condition=pipeline_stages.STAGE_ENABLED_CONDITIONS.get(operation_id),
        )
        for operation_id in pipeline_stages.OPERATION_ORDER
    )
