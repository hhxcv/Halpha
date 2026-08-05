"""Typed HTTP contracts owned by the local workbench API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from halpha.capital.models import StopStateVersion
from halpha.outcomes.models import Review
from halpha.planning.models import PlanActivation
from halpha.planning.models import PlanDecisionContext, PositionAlignmentSpec
from halpha.planning.order_schedule import (
    OrderSchedulePreview,
    OrderScheduleSpec,
)
from halpha.planning.registry import (
    DecisionBasisKind,
    Direction,
    DraftDecisionBasis,
    PlanKeyParameterDefinition,
)
from halpha.planning.transitions import ControlIntent


class FrozenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AccountPositionResponse(FrozenResponse):
    instrument_ref: str
    symbol: str
    direction: Literal["LONG", "SHORT"]
    position_side: Literal["BOTH", "LONG", "SHORT"]
    quantity: str
    absolute_quantity: str
    entry_price: str
    break_even_price: str | None
    mark_price: str
    unrealized_pnl: str
    liquidation_price: str | None
    leverage: int
    margin_mode: Literal["CROSS", "ISOLATED"]
    notional: str
    isolated_margin: str | None
    fact_cutoff: str
    snapshot_ref: str
    origin: Literal[
        "EXTERNAL_UNMANAGED",
        "ACCOUNT_TOTAL_WITH_HALPHA_ATTRIBUTION",
    ]
    management_status: Literal["OBSERVED_ONLY"]
    takeover_allowed: bool
    takeover_blockers: list[
        Literal[
            "READ_ONLY_CREDENTIAL",
            "ACCOUNT_POSITION_SNAPSHOT_NOT_CURRENT",
            "ATTRIBUTION_REQUIRES_RECONCILIATION",
            "OPEN_ORDERS_REQUIRE_RECONCILIATION",
        ]
    ]


class AccountOrderResponse(FrozenResponse):
    kind: Literal["ORDINARY", "ALGO"]
    instrument_ref: str
    symbol: str
    order_id: str
    client_order_id: str | None
    side: Literal["BUY", "SELL"]
    position_side: Literal["BOTH", "LONG", "SHORT"]
    order_type: str
    status: str
    time_in_force: str | None
    price: str | None
    trigger_price: str | None
    quantity: str | None
    executed_quantity: str | None
    reduce_only: bool | None
    close_position: bool | None
    source_create_time_ms: int | None
    source_update_time_ms: int | None
    fact_cutoff: str
    snapshot_ref: str


class OverviewResponse(FrozenResponse):
    environment_kind: str
    environment_id: str
    account_id: str
    profile: str
    authority_class: str
    runtime_real_write_gate: str
    server_fact_cutoff: str
    view_retrieved_at: str
    open_activation_count: int
    database_name: str
    account_snapshot_status: Literal[
        "CURRENT",
        "STALE",
        "UNAVAILABLE",
        "UNKNOWN",
    ]
    account_snapshot_ref: str | None
    account_snapshot_cutoff: str | None
    account_snapshot_age_seconds: int | None
    account_ordinary_open_order_count: int | None
    account_algo_open_order_count: int | None
    account_positions: list[AccountPositionResponse]
    account_orders: list[AccountOrderResponse]


class AccountPositionOperationPreviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["REDUCE", "CLOSE", "ADD"]
    snapshot_ref: str = Field(min_length=1, max_length=160)
    fact_cutoff: str
    instrument_ref: str = Field(min_length=1, max_length=96)
    position_side: Literal["BOTH", "LONG", "SHORT"]
    expected_absolute_quantity: str
    requested_quantity: str | None = None
    requested_notional: str | None = None


class AccountPositionOperationPlanPrefill(FrozenResponse):
    kind: Literal["POSITION_DISPOSITION", "NEW_EXPOSURE"]
    plan_name: str
    instrument_ref: str
    direction: Literal["LONG", "SHORT"]
    trade_amount: str
    valid_minutes: int
    baseline_quantity: str
    target_quantity_after: str | None
    position_alignment: PositionAlignmentSpec | None


class AccountPositionOperationPreviewResponse(FrozenResponse):
    operation: Literal["REDUCE", "CLOSE", "ADD"]
    snapshot_ref: str
    fact_cutoff: str
    instrument_ref: str
    position_side: Literal["BOTH", "LONG", "SHORT"]
    direction: Literal["LONG", "SHORT"]
    preparation_allowed: bool
    activation_allowed: bool
    venue_action_created: Literal[False]
    blockers: list[
        Literal[
            "READ_ONLY_CREDENTIAL",
            "OPEN_ORDERS_REQUIRE_RECONCILIATION",
            "ATTRIBUTION_REQUIRES_RECONCILIATION",
            "HEDGE_MODE_POSITION_OPERATIONS_UNSUPPORTED",
            "EXTERNAL_POSITION_REQUIRES_ALIGNMENT",
        ]
    ]
    plan_prefill: AccountPositionOperationPlanPrefill


class OrderSchedulePreviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule_ref: str
    decision_basis_kind: DecisionBasisKind = DecisionBasisKind.DIRECT_EXECUTION
    venue_ref: Literal["BINANCE_USDM"] = "BINANCE_USDM"
    instrument_ref: str
    direction: Direction
    max_notional: str
    reference_price: str | None = None
    spec: OrderScheduleSpec


class TradingContextTargetResponse(FrozenResponse):
    venue_account_type: Literal[
        "USDM_DEMO",
        "USDM_COPY_LEAD",
        "USDM_PERSONAL",
    ]
    environment_id: str
    account_id: str
    url: str


class SettingsStatusResponse(FrozenResponse):
    environment_kind: str
    environment_id: str
    account_id: str
    venue_account_type: Literal[
        "USDM_DEMO",
        "USDM_COPY_LEAD",
        "USDM_PERSONAL",
    ]
    profile: str
    authority_class: str
    bind: str
    port: int
    trading_contexts: list[TradingContextTargetResponse]
    database_name: str
    database_available: bool
    database_reason_code: str | None
    server_fact_cutoff: str | None
    product_build_id: str
    app_executor_product_build_consistent: bool | None
    executor_status: str
    executor_status_checked_at: str
    configured_runtime_real_write_gate: str
    runtime_real_write_gate: str
    live_write_gate_violations: list[str]
    authorized_activation_ids: list[str]
    email_delivery_enabled: bool
    email_configuration_status: str
    view_retrieved_at: str


class StrategySummaryResponse(FrozenResponse):
    strategy_id: str
    strategy_version: str
    display_name: str
    value_logic: str
    applicable_scenarios: str
    execution_behavior: str
    parameter_schema_version: str
    supported_directions: list[Direction]
    economic_scope: dict[str, Any]
    plan_key_parameters: list[PlanKeyParameterDefinition]


class ActivationPreviewResponse(FrozenResponse):
    plan_version_id: str
    plan_name: str | None
    created_at: str | None
    creator_kind: Literal["HUMAN", "AI"] | None
    decision_context: PlanDecisionContext | None = None
    environment_id: str
    environment_kind: str
    authority_class: str
    account_ref: str
    venue_ref: str
    instrument_ref: str
    direction: Direction
    decision_basis: dict[str, Any]
    decision_basis_kind: DecisionBasisKind
    decision_basis_ref: str
    strategy_ref: str | None
    parameter_digest: str
    strategy_parameters: dict[str, Any]
    order_schedule_spec: OrderScheduleSpec | None
    position_alignment: PositionAlignmentSpec | None
    trade_amount: str
    limits: dict[str, Any]
    valid_until: str
    allowed_actions: list[str]
    actual_account_configuration: str
    account_mode_policy: str
    product_build_id: str
    product_build_consistent: bool
    runtime_compatible: bool
    runtime_incompatibility_reason: str | None
    position_alignment_ready: bool | None
    position_alignment_blocker: str | None
    configured_runtime_real_write_gate: str
    runtime_real_write_gate: str
    live_activation_eligible: bool
    capital_notice: str
    order_schedule_snapshot: OrderSchedulePreview | None
    expected_schedule_digest: str | None
    executor_status: str
    executor_status_checked_at: str


class PlanSummaryResponse(FrozenResponse):
    plan_id: str
    draft_version: int
    draft_content_digest: str
    updated_at: str
    plan_name: str | None
    created_at: str | None
    creator_kind: Literal["HUMAN", "AI"] | None
    decision_context: PlanDecisionContext | None = None
    decision_basis: DraftDecisionBasis
    decision_basis_kind: DecisionBasisKind
    decision_basis_ref: str
    strategy_id: str | None
    instrument_ref: str
    direction: Direction
    parameters: dict[str, Any]
    order_schedule_spec: OrderScheduleSpec | None
    position_alignment: PositionAlignmentSpec | None
    max_notional: str
    valid_from: str
    valid_until: str
    plan_version_id: str | None
    fixed_at: str | None
    fixed_content_digest: str | None
    fixed_product_build_id: str | None
    fixed_valid_until: str | None
    product_build_consistent: bool | None
    runtime_compatible: bool | None
    runtime_incompatibility_reason: str | None


class PlanDeleteResponse(FrozenResponse):
    result: Literal["APPLIED"]
    plan_id: str
    deleted_draft_version: int


class ActivationCreateResponse(FrozenResponse):
    activation: PlanActivation
    venue_write_created: bool
    runtime_real_write_gate: str


class ActivationSummaryResponse(PlanActivation):
    plan_name: str | None
    plan_created_at: str | None
    plan_creator_kind: str | None
    closure_reason_code: str | None
    primary_result: str | None
    trade_result: dict[str, Any] | None


class ActivationDetailResponse(FrozenResponse):
    activation: PlanActivation
    plan: dict[str, Any]
    decision_basis: dict[str, Any]
    strategy: dict[str, Any] | None
    order_schedule: OrderSchedulePreview | None
    capital: dict[str, Any]
    position_attribution: dict[str, Any]
    trade_result: dict[str, Any]
    execution_actions: list[dict[str, Any]]
    venue_facts: list[dict[str, Any]]
    receipts: list[dict[str, Any]]
    stopped_categories: list[str]
    stop_evidence: list[dict[str, Any]]
    runtime_real_write_gate: str


class ActivationTimelineEntryResponse(FrozenResponse):
    source: Literal[
        "ACTIVATION",
        "PLAN_EVENT",
        "EXECUTION_ACTION",
        "VENUE_FACT",
        "CONTROL_COMMAND",
    ]
    source_ref: str
    stage_order: int
    at: str
    status: str
    detail: dict[str, Any]


class ControlPreviewResponse(ActivationDetailResponse):
    intent: ControlIntent
    consequence: str
    preview_digest: str
    previewed_at: str
    resume_eligible: bool | None
    resume_denial_reasons: list[str]
    reconciliation_digest: str | None
    reconciliation_evidence_cutoff: str | None
    venue_write_created_by_preview: Literal[False]


class SystemStopSummaryResponse(FrozenResponse):
    stop_state_version_id: str
    version: int
    source: str
    started_at: str


class SystemStopReleasePreviewResponse(FrozenResponse):
    eligible: bool
    denial_reasons: list[str]
    consequence: str
    stop: SystemStopSummaryResponse | None
    evidence_cutoff: str | None


class SystemStopReleaseResponse(FrozenResponse):
    effective: Literal[True]
    replayed: bool
    stop_state: StopStateVersion


class ReceiptResponse(FrozenResponse):
    receipt_id: str
    command_id: str
    processing_owner: str
    state: str
    state_version: int
    reason_code: str | None
    result: dict[str, Any] | None
    pending_responsibility_refs: list[str]
    content_digest: str
    created_at: str
    updated_at: str


class ReviewResponse(Review):
    trade_context: dict[str, Any]
    resolved_trade_result: dict[str, Any]


class ExecutionFeeSampleResponse(FrozenResponse):
    conservative_rate_bps: str
    sample_count: int
    latest_fill_time: str


class ExecutionFeeEvidenceResponse(FrozenResponse):
    instrument_ref: str
    source: Literal["RECENT_ATTRIBUTED_COMPLETED_FILLS"]
    calculation: Literal["MAX_RATE_OF_LATEST_FILLS"]
    sample_limit: int
    maker: ExecutionFeeSampleResponse | None
    taker: ExecutionFeeSampleResponse | None
    source_cutoff: str | None


class ReviewHistoryResponse(FrozenResponse):
    review: ReviewResponse
    versions: list[ReviewResponse]


class ReviewCompletionResponse(FrozenResponse):
    review: Review


class TestEmailResponse(FrozenResponse):
    status: Literal["DELIVERED"]
    environment_id: str
    recipient_route_ref: str
    delivered_at: str
    business_state_changed: Literal[False]
