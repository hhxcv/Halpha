"""Fail-closed account-position operation previews for the workbench."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from halpha.app.api_models import (
    AccountPositionOperationPreviewPayload,
    AccountPositionOperationPreviewResponse,
)
from halpha.domain_values import canonical_decimal, decimal_from_string
from halpha.planning.models import PositionAlignmentSpec


def _positive(value: str, *, code: str) -> Decimal:
    return decimal_from_string(value, code=code, positive=True)


def preview_account_position_operation(
    summary: dict[str, Any],
    payload: AccountPositionOperationPreviewPayload,
    *,
    profile: str,
    account_ref: str,
) -> AccountPositionOperationPreviewResponse:
    """Bind one preview to the latest complete account snapshot.

    This boundary never writes a plan, action, or venue order.  A later plan
    activation revalidates the same immutable baseline and the Executor still
    refreshes venue facts immediately before a reduce-only submission.
    """

    if summary.get("account_snapshot_status") != "CURRENT":
        raise ValueError("ACCOUNT_POSITION_SNAPSHOT_NOT_CURRENT")
    if (
        summary.get("account_snapshot_ref") != payload.snapshot_ref
        or summary.get("account_snapshot_cutoff") != payload.fact_cutoff
    ):
        raise ValueError("ACCOUNT_POSITION_SNAPSHOT_CHANGED")
    positions = summary.get("account_positions")
    if not isinstance(positions, list):
        raise ValueError("ACCOUNT_POSITION_SNAPSHOT_INVALID")
    matches = [
        item
        for item in positions
        if isinstance(item, dict)
        and item.get("instrument_ref") == payload.instrument_ref
        and item.get("position_side") == payload.position_side
    ]
    if len(matches) != 1:
        raise ValueError("ACCOUNT_POSITION_SNAPSHOT_CHANGED")
    position = matches[0]
    baseline = _positive(
        str(position.get("absolute_quantity", "")),
        code="ACCOUNT_POSITION_QUANTITY_INVALID",
    )
    expected = _positive(
        payload.expected_absolute_quantity,
        code="ACCOUNT_POSITION_QUANTITY_INVALID",
    )
    if baseline != expected:
        raise ValueError("ACCOUNT_POSITION_SNAPSHOT_CHANGED")
    mark = _positive(
        str(position.get("mark_price", "")),
        code="ACCOUNT_POSITION_PRICE_INVALID",
    )
    entry = _positive(
        str(position.get("entry_price", "")),
        code="ACCOUNT_POSITION_PRICE_INVALID",
    )
    direction = str(position.get("direction", ""))
    if direction not in {"LONG", "SHORT"}:
        raise ValueError("ACCOUNT_POSITION_DIRECTION_INVALID")

    operation = payload.operation
    alignment: PositionAlignmentSpec | None = None
    target_after: str | None
    if operation == "REDUCE":
        if payload.requested_quantity is None or payload.requested_notional is not None:
            raise ValueError("POSITION_OPERATION_QUANTITY_REQUIRED")
        reduction = _positive(
            payload.requested_quantity,
            code="POSITION_OPERATION_QUANTITY_INVALID",
        )
        if reduction >= baseline:
            raise ValueError("POSITION_REDUCTION_MUST_LEAVE_POSITION")
        target = baseline - reduction
        trade_amount = reduction * mark
        target_after = canonical_decimal(target)
    elif operation == "CLOSE":
        if payload.requested_quantity is not None or payload.requested_notional is not None:
            raise ValueError("POSITION_CLOSE_QUANTITY_IS_SNAPSHOT_BOUND")
        reduction = baseline
        trade_amount = baseline * mark
        target_after = "0"
    else:
        if payload.requested_quantity is not None or payload.requested_notional is None:
            raise ValueError("POSITION_ADD_NOTIONAL_REQUIRED")
        trade_amount = _positive(
            payload.requested_notional,
            code="POSITION_ADD_NOTIONAL_INVALID",
        )
        reduction = Decimal(0)
        target_after = None

    blockers: list[str] = []
    if profile == "BINANCE_LIVE_READ_ONLY":
        blockers.append("READ_ONLY_CREDENTIAL")
    if int(summary.get("account_ordinary_open_order_count") or 0) > 0 or int(
        summary.get("account_algo_open_order_count") or 0
    ) > 0:
        blockers.append("OPEN_ORDERS_REQUIRE_RECONCILIATION")
    if position.get("origin") == "ACCOUNT_TOTAL_WITH_HALPHA_ATTRIBUTION":
        blockers.append("ATTRIBUTION_REQUIRES_RECONCILIATION")
    if operation == "ADD" and payload.position_side != "BOTH":
        blockers.append("HEDGE_MODE_POSITION_OPERATIONS_UNSUPPORTED")
    if operation == "ADD" and position.get("origin") == "EXTERNAL_UNMANAGED":
        blockers.append("EXTERNAL_POSITION_REQUIRES_ALIGNMENT")

    normalized_notional = canonical_decimal(trade_amount)
    if operation in {"REDUCE", "CLOSE"}:
        alignment = PositionAlignmentSpec(
            operation=operation,
            snapshot_ref=payload.snapshot_ref,
            fact_cutoff=payload.fact_cutoff,
            account_ref=account_ref,
            venue_ref="BINANCE_USDM",
            instrument_ref=payload.instrument_ref,
            direction=direction,
            position_side=payload.position_side,
            baseline_quantity=canonical_decimal(baseline),
            requested_reduction_quantity=canonical_decimal(reduction),
            target_quantity_after=target_after,
            baseline_entry_price=canonical_decimal(entry),
            baseline_mark_price=canonical_decimal(mark),
        )
        kind = "POSITION_DISPOSITION"
        plan_name = (
            f"{payload.instrument_ref} "
            f"{'减仓' if operation == 'REDUCE' else '平仓'}处置"
        )
    else:
        kind = "NEW_EXPOSURE"
        plan_name = f"{payload.instrument_ref} 独立追加开仓"

    return AccountPositionOperationPreviewResponse(
        operation=operation,
        snapshot_ref=payload.snapshot_ref,
        fact_cutoff=payload.fact_cutoff,
        instrument_ref=payload.instrument_ref,
        position_side=payload.position_side,
        direction=direction,
        preparation_allowed=True,
        activation_allowed=not blockers,
        venue_action_created=False,
        blockers=blockers,
        plan_prefill={
            "kind": kind,
            "plan_name": plan_name,
            "instrument_ref": payload.instrument_ref,
            "direction": direction,
            "trade_amount": normalized_notional,
            "valid_minutes": 60,
            "baseline_quantity": canonical_decimal(baseline),
            "target_quantity_after": target_after,
            "position_alignment": alignment,
        },
    )
