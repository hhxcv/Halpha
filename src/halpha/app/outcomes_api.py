"""App boundary for OUT review operations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import psycopg
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from halpha.outcomes.repository import PostgreSQLOutcomeRepository
from halpha.outcomes.models import ReviewClassification, StageReviewCreator
from halpha.outcomes.account_reconciliation import account_result_role
from halpha.outcomes.service import OutcomeApplicationService
from halpha.outcomes.trade_result import summarize_trade_result
from halpha.domain_values import canonical_decimal


_EXECUTION_FEE_SAMPLE_LIMIT = 10


class OutcomeApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewRefreshPayload(OutcomeApiModel):
    expected_version: int = Field(gt=0)


class ReviewCompletionPayload(OutcomeApiModel):
    expected_version: int = Field(gt=0)
    conclusion: ReviewClassification
    note: str = Field(default="", max_length=2000)


class StageReviewCreatePayload(OutcomeApiModel):
    title: str = Field(min_length=1, max_length=160)
    range_start: datetime
    range_end: datetime
    problem_analysis: str = Field(min_length=1, max_length=8000)
    improvement_plan: str = Field(min_length=1, max_length=8000)
    creator_kind: StageReviewCreator


class OutcomesApiUnavailable(RuntimeError):
    """Sanitized failure to reach the OUT application database boundary."""


class PostgreSQLOutcomesApi:
    def __init__(
        self,
        *,
        database_name: str,
        database_role_name: str,
        password: SecretStr,
        environment_id: str,
        read_only: bool = False,
    ) -> None:
        self._database_name = database_name
        self._database_role_name = database_role_name
        self._password = password
        self._environment_id = environment_id
        self._read_only = read_only

    def _connect(self) -> psycopg.Connection[Any]:
        try:
            return psycopg.connect(
                host="127.0.0.1",
                port=5432,
                dbname=self._database_name,
                user=self._database_role_name,
                password=self._password.get_secret_value(),
                connect_timeout=2,
                options=(
                    "-c default_transaction_read_only=on"
                    if self._read_only
                    else None
                ),
            )
        except Exception as exc:
            raise OutcomesApiUnavailable(
                f"OUTCOMES_DATABASE_UNAVAILABLE type={type(exc).__name__}"
            ) from None

    def _require_product_mutation_allowed(self) -> None:
        if self._read_only:
            raise ValueError("LIVE_READ_ONLY_PRODUCT_MUTATION_FORBIDDEN")

    def list_reviews(self) -> list[dict[str, Any]]:
        with self._connect() as connection, connection.transaction():
            reviews = OutcomeApplicationService(
                connection, self._environment_id
            ).list_reviews()
            return self._attach_trade_context(connection, reviews)

    def execution_fee_evidence(self, instrument_ref: str) -> dict[str, Any]:
        with self._connect() as connection, connection.transaction():
            reviews = OutcomeApplicationService(
                connection, self._environment_id
            ).list_reviews()
            resolved_reviews = self._attach_trade_context(connection, reviews)
            return summarize_execution_fee_evidence(
                resolved_reviews,
                instrument_ref=instrument_ref,
                sample_limit=_EXECUTION_FEE_SAMPLE_LIMIT,
            )

    def list_stage_reviews(self) -> list[dict[str, Any]]:
        with self._connect() as connection, connection.transaction():
            return OutcomeApplicationService(
                connection,
                self._environment_id,
            ).list_stage_reviews()

    def create_stage_review(
        self,
        payload: StageReviewCreatePayload,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._require_product_mutation_allowed()
        with self._connect() as connection, connection.transaction():
            review = OutcomeApplicationService(
                connection,
                self._environment_id,
            ).create_stage_review(
                idempotency_key=idempotency_key,
                title=payload.title,
                range_start=payload.range_start,
                range_end=payload.range_end,
                problem_analysis=payload.problem_analysis,
                improvement_plan=payload.improvement_plan,
                creator_kind=payload.creator_kind,
                observed_at=datetime.now(UTC),
            )
            return review.model_dump(mode="json")

    def read_review(self, review_id: str) -> dict[str, Any]:
        with self._connect() as connection, connection.transaction():
            result = OutcomeApplicationService(
                connection, self._environment_id
            ).read_review(review_id)
            versions = self._attach_trade_context(
                connection,
                list(result["versions"]),
            )
            result["versions"] = versions
            result["review"] = versions[0]
            return result

    def _attach_trade_context(
        self,
        connection: psycopg.Connection[Any],
        reviews: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        activation_ids = [str(item["activation_id"]) for item in reviews]
        if not activation_ids:
            return reviews
        rows = connection.execute(
            """
            SELECT a.activation_id, a.instrument_ref, a.direction,
                   a.decision_basis_ref,
                   v.max_notional, a.created_at, a.updated_at,
                   v.terms ->> 'plan_name',
                   v.terms ->> 'created_at',
                   v.terms ->> 'creator_kind',
                   a.order_schedule_snapshot,
                   a.position_alignment
            FROM halpha.plan_activation a
            LEFT JOIN halpha.trade_plan_version v
              ON v.environment_id = a.environment_id
             AND v.plan_version_id = a.plan_version_ref
            WHERE a.environment_id = %s AND a.activation_id::text = ANY(%s)
            """,
            (self._environment_id, activation_ids),
        ).fetchall()
        contexts = {
            str(row[0]): {
                "instrument_ref": str(row[1]),
                "direction": str(row[2]),
                "decision_basis_ref": str(row[3]),
                "strategy_id": (
                    None
                    if str(row[3]) == "DIRECT_EXECUTION@1"
                    else str(row[3]).split("@", maxsplit=1)[0]
                ),
                "trade_amount": str(row[4]) if row[4] is not None else None,
                "activation_started_at": row[5].isoformat(),
                "activation_updated_at": row[6].isoformat(),
                "plan_name": str(row[7]) if row[7] is not None else None,
                "plan_created_at": str(row[8]) if row[8] is not None else None,
                "plan_creator_kind": str(row[9]) if row[9] is not None else None,
                "order_schedule_snapshot": (
                    dict(row[10]) if row[10] is not None else None
                ),
                "position_alignment": (
                    dict(row[11])
                    if len(row) > 11 and row[11] is not None
                    else None
                ),
            }
            for row in rows
        }
        action_rows = connection.execute(
            """
            SELECT activation_id, execution_action_id, action_kind
            FROM halpha.execution_action
            WHERE environment_id = %s AND activation_id::text = ANY(%s)
            """,
            (self._environment_id, activation_ids),
        ).fetchall()
        fact_rows = connection.execute(
            """
            SELECT COALESCE(
                     activation_ref::text,
                     impact_scope ->> 'account_episode_activation_id'
                   ) AS account_episode_activation_id,
                   venue_fact_id, schema_version, kind, content_digest,
                   payload, action_ref, source_time, impact_scope,
                   attribution_class
            FROM halpha.venue_fact
            WHERE environment_id = %s
              AND (
                activation_ref::text = ANY(%s)
                OR (
                  attribution_class IS NULL
                  AND impact_scope ->> 'account_episode_activation_id' = ANY(%s)
                )
              )
            """,
            (self._environment_id, activation_ids, activation_ids),
        ).fetchall()
        actions_by_activation: dict[str, dict[str, tuple[Any, ...]]] = {}
        for row in action_rows:
            actions_by_activation.setdefault(str(row[0]), {})[str(row[1])] = row
        facts_by_activation: dict[str, dict[str, tuple[Any, ...]]] = {}
        for row in fact_rows:
            facts_by_activation.setdefault(str(row[0]), {})[str(row[1])] = row

        def resolved_trade_result(review: dict[str, Any]) -> dict[str, Any]:
            activation_id = str(review["activation_id"])
            input_refs = review.get("input_refs")
            if not isinstance(input_refs, dict):
                return _unresolved_trade_result(("input_refs",))
            action_refs = input_refs.get("execution_actions", [])
            fact_refs = input_refs.get("venue_facts", [])
            if not isinstance(action_refs, list) or not isinstance(fact_refs, list):
                return _unresolved_trade_result(("input_refs",))
            if any(
                not isinstance(item, dict)
                or item.get("execution_action_id") is None
                for item in action_refs
            ) or any(
                not isinstance(item, dict) or item.get("venue_fact_id") is None
                for item in fact_refs
            ):
                return _unresolved_trade_result(("input_refs",))
            expected_action_refs = tuple(action_refs)
            expected_fact_refs = tuple(fact_refs)
            expected_actions = tuple(
                dict.fromkeys(
                    str(item["execution_action_id"])
                    for item in expected_action_refs
                )
            )
            expected_facts = tuple(
                dict.fromkeys(
                    str(item["venue_fact_id"]) for item in expected_fact_refs
                )
            )
            available_actions = actions_by_activation.get(activation_id, {})
            available_facts = facts_by_activation.get(activation_id, {})
            unresolved_refs = tuple(
                sorted(
                    {
                        *(
                            f"execution_action:{item}"
                            for item in expected_actions
                            if item not in available_actions
                        ),
                        *(
                            f"venue_fact:{item}"
                            for item in expected_facts
                            if item not in available_facts
                        ),
                        *(
                            f"venue_fact:{item['venue_fact_id']}:snapshot_mismatch"
                            for item in expected_fact_refs
                            if str(item["venue_fact_id"]) in available_facts
                            and not _fact_matches_snapshot(
                                available_facts[str(item["venue_fact_id"])],
                                item,
                            )
                        ),
                    }
                )
            )
            if unresolved_refs:
                return _unresolved_trade_result(unresolved_refs)
            context = contexts.get(activation_id, {})
            result = summarize_trade_result(
                direction=str(context.get("direction", "")),
                action_kinds={
                    action_id: str(available_actions[action_id][2])
                    for action_id in expected_actions
                },
                facts=(
                    {
                        "kind": str(available_facts[fact_id][3]),
                        "payload": dict(available_facts[fact_id][5]),
                        "action_ref": (
                            str(available_facts[fact_id][6])
                            if available_facts[fact_id][6] is not None
                            else None
                        ),
                        "source_time": (
                            available_facts[fact_id][7].isoformat()
                            if available_facts[fact_id][7] is not None
                            else None
                        ),
                        "result_role": account_result_role(
                            available_facts[fact_id][8]
                        ),
                    }
                    for fact_id in expected_facts
                ),
                opening_position_quantity=(
                    str(context["position_alignment"]["requested_reduction_quantity"])
                    if isinstance(context.get("position_alignment"), dict)
                    and context["position_alignment"].get(
                        "requested_reduction_quantity"
                    ) is not None
                    else None
                ),
            )
            return {**result, "unresolved_refs": []}
        return [
            {
                **item,
                "trade_context": contexts.get(str(item["activation_id"]), {}),
                "resolved_trade_result": resolved_trade_result(item),
            }
            for item in reviews
        ]

    def refresh_review(
        self, review_id: str, payload: ReviewRefreshPayload
    ) -> dict[str, Any]:
        self._require_product_mutation_allowed()
        with self._connect() as connection, connection.transaction():
            repository = PostgreSQLOutcomeRepository(connection, self._environment_id)
            current = repository.get_review(review_id, payload.expected_version)
            refreshed = OutcomeApplicationService(
                connection, self._environment_id
            ).update_activation_review(
                current.activation_id,
                fact_cutoff=datetime.now(UTC),
                observed_at=datetime.now(UTC),
                expected_version=payload.expected_version,
            )
            return refreshed.model_dump(mode="json")

    def complete_review(
        self, review_id: str, payload: ReviewCompletionPayload
    ) -> dict[str, Any]:
        self._require_product_mutation_allowed()
        with self._connect() as connection, connection.transaction():
            review = OutcomeApplicationService(
                connection, self._environment_id
            ).complete_activation_review(
                review_id,
                expected_version=payload.expected_version,
                conclusion=payload.conclusion,
                note=payload.note,
                observed_at=datetime.now(UTC),
            )
            return {"review": review.model_dump(mode="json")}


def _unresolved_trade_result(unresolved_refs: tuple[str, ...]) -> dict[str, Any]:
    return {
        "fill_count": 0,
        "fills": [],
        "position_quantity": None,
        "average_entry_price": None,
        "average_exit_price": None,
        "entry_notional": None,
        "fill_cash_flow": None,
        "commission": None,
        "commission_complete": False,
        "funding": None,
        "funding_record_count": 0,
        "funding_complete": False,
        "calculation_complete": False,
        "execution_cost_complete": False,
        "closed": False,
        "gross_pnl": None,
        "net_pnl": None,
        "currency": "USDT",
        "funding_included": False,
        "fill_times_complete": False,
        "first_fill_time": None,
        "last_fill_time": None,
        "holding_duration_seconds": None,
        "result_scope": "UNKNOWN",
        "external_closure_fill_count": 0,
        "strategy_attribution_complete": False,
        "unresolved_refs": list(unresolved_refs),
    }


def summarize_execution_fee_evidence(
    reviews: Iterable[Mapping[str, Any]],
    *,
    instrument_ref: str,
    sample_limit: int = _EXECUTION_FEE_SAMPLE_LIMIT,
) -> dict[str, Any]:
    """Project recent exact fill commissions without claiming a current venue rate."""

    if sample_limit < 1:
        raise ValueError("EXECUTION_FEE_SAMPLE_LIMIT_INVALID")
    samples: dict[str, dict[str, tuple[datetime, Decimal]]] = {
        "MAKER": {},
        "TAKER": {},
    }
    for review in reviews:
        context = review.get("trade_context")
        result = review.get("resolved_trade_result")
        if (
            not isinstance(context, Mapping)
            or str(context.get("instrument_ref", "")) != instrument_ref
            or not isinstance(result, Mapping)
            or result.get("closed") is not True
            or result.get("calculation_complete") is not True
            or result.get("commission_complete") is not True
            or result.get("strategy_attribution_complete") is not True
        ):
            continue
        activation_id = str(review.get("activation_id", ""))
        fills = result.get("fills")
        if not activation_id or not isinstance(fills, list):
            continue
        for fill in fills:
            if not isinstance(fill, Mapping):
                continue
            liquidity_side = str(fill.get("liquidity_side", ""))
            trade_id = str(fill.get("trade_id", ""))
            if (
                liquidity_side not in samples
                or not trade_id
                or str(fill.get("fee_currency", "")) != "USDT"
            ):
                continue
            try:
                notional = Decimal(str(fill.get("notional", "")))
                fee = Decimal(str(fill.get("fee", "")))
                fill_time = _fee_fill_time(fill.get("fill_time"))
            except (InvalidOperation, ValueError):
                continue
            if notional <= 0 or fee < 0 or fill_time is None:
                continue
            samples[liquidity_side][f"{activation_id}:{trade_id}"] = (
                fill_time,
                fee / notional * Decimal("10000"),
            )

    projected = {
        side: _fee_sample_projection(side_samples.values(), sample_limit)
        for side, side_samples in samples.items()
    }
    cutoffs = tuple(
        sample["latest_fill_time"]
        for sample in projected.values()
        if sample is not None
    )
    return {
        "instrument_ref": instrument_ref,
        "source": "RECENT_ATTRIBUTED_COMPLETED_FILLS",
        "calculation": "MAX_RATE_OF_LATEST_FILLS",
        "sample_limit": sample_limit,
        "maker": projected["MAKER"],
        "taker": projected["TAKER"],
        "source_cutoff": max(cutoffs) if cutoffs else None,
    }


def _fee_fill_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _fee_sample_projection(
    samples: Iterable[tuple[datetime, Decimal]],
    sample_limit: int,
) -> dict[str, Any] | None:
    latest = sorted(samples, key=lambda item: item[0], reverse=True)[:sample_limit]
    if not latest:
        return None
    return {
        "conservative_rate_bps": canonical_decimal(max(item[1] for item in latest)),
        "sample_count": len(latest),
        "latest_fill_time": latest[0][0].isoformat(),
    }


def _fact_matches_snapshot(row: tuple[Any, ...], snapshot: dict[str, Any]) -> bool:
    return (
        (
            snapshot.get("schema_version") is None
            or int(snapshot["schema_version"]) == int(row[2])
        )
        and (snapshot.get("kind") is None or str(snapshot["kind"]) == str(row[3]))
        and (
            snapshot.get("content_digest") is None
            or str(snapshot["content_digest"]) == str(row[4])
        )
    )
