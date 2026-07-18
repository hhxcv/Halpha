"""Authenticated B02 App boundary for plans, limits, and activation transactions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import psycopg
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from halpha.capital.models import (
    AccountCapitalLimitVersion,
    AuthorityClass,
    EnvironmentKind,
)
from halpha.capital.repository import PostgreSQLCapitalRepository
from halpha.domain_values import canonical_decimal, content_digest, decimal_from_string
from halpha.live_write_gate import (
    GateStatusProvider,
    LiveWriteGateStatus,
    closed_live_write_gate_status,
)
from halpha.planning.models import RequestedLimits, TradePlanContent
from halpha.planning.control_service import ActivationControlService
from halpha.planning.registry import (
    describe_strategy,
    list_strategies,
    strategy_parameter_schema,
)
from halpha.planning.repository import PlanningConflict, PostgreSQLPlanningRepository
from halpha.planning.service import PlanningApplicationService
from halpha.planning.transitions import ControlIntent
from halpha.user_workbench.commands import build_command


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlanDraftPayload(ApiModel):
    strategy_id: str
    parameters: dict[str, Any]
    venue_ref: str = "BINANCE_USDM"
    instrument_ref: str
    direction: str
    target_exposure: str
    max_margin: str
    max_notional: str
    max_allowed_loss: str
    valid_minutes: int = Field(ge=15, le=10080)

    @field_validator(
        "target_exposure",
        "max_margin",
        "max_notional",
        "max_allowed_loss",
    )
    @classmethod
    def exact_positive_decimal(cls, value: str) -> str:
        return canonical_decimal(
            decimal_from_string(value, code="PLAN_VALUE_INVALID", positive=True)
        )


class CapitalLimitPayload(ApiModel):
    quote_asset: str = "USDT"
    max_margin: str
    max_notional: str
    max_allowed_loss: str
    max_action_notional: str
    instruments: list[str]

    @field_validator(
        "max_margin",
        "max_notional",
        "max_allowed_loss",
        "max_action_notional",
    )
    @classmethod
    def exact_positive_decimal(cls, value: str) -> str:
        return canonical_decimal(
            decimal_from_string(value, code="CAPITAL_LIMIT_INVALID", positive=True)
        )


class ActivationPayload(ApiModel):
    plan_version_id: str
    capital_limit_version_id: str
    quote_asset: str = "USDT"
    owner_password: str
    real_capital_acknowledged: bool = False
    evidence_limitations_acknowledged: bool = False
    online_monitoring_acknowledged: bool = False


class ControlPayload(ApiModel):
    expected_version: int = Field(gt=0)
    owner_password: str
    takeover_scope: dict[str, Any] = Field(default_factory=dict)


class TaskAcknowledgePayload(ApiModel):
    expected_version: int = Field(gt=0)


class PlanningApiUnavailable(RuntimeError):
    pass


def _stable_id(environment_id: str, kind: str, idempotency_key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"urn:halpha:{environment_id}:{kind}:{idempotency_key}"))


class PostgreSQLPlanningApi:
    def __init__(
        self,
        *,
        database_name: str,
        password: SecretStr,
        environment_id: str,
        environment_kind: str,
        authority_class: str,
        account_ref: str,
        build_digest: str | None,
        profile: str | None = None,
        gate_status_provider: GateStatusProvider | None = None,
    ) -> None:
        self._database_name = database_name
        self._password = password
        self._environment_id = environment_id
        self._environment_kind = EnvironmentKind(environment_kind)
        self._authority_class = AuthorityClass(authority_class)
        self._account_ref = account_ref
        self._build_digest = build_digest
        self._profile = profile or (
            "BINANCE_DEMO"
            if self._environment_kind is EnvironmentKind.DEMO
            else (
                "BINANCE_LIVE_WRITE"
                if self._authority_class is AuthorityClass.LIVE_REAL_CAPITAL
                else "BINANCE_LIVE_READ_ONLY"
            )
        )
        self._gate_status_provider = (
            gate_status_provider or closed_live_write_gate_status
        )

    def _gate_status(self) -> LiveWriteGateStatus:
        try:
            return self._gate_status_provider()
        except Exception:
            return closed_live_write_gate_status()

    def _connect(self) -> psycopg.Connection[Any]:
        try:
            return psycopg.connect(
                host="127.0.0.1",
                port=5432,
                dbname=self._database_name,
                user=f"{self._database_name}_app",
                password=self._password.get_secret_value(),
                connect_timeout=2,
            )
        except Exception as exc:
            raise PlanningApiUnavailable(
                f"PLANNING_DATABASE_UNAVAILABLE type={type(exc).__name__}"
            ) from None

    def strategies(self) -> list[dict[str, Any]]:
        return [
            {
                "strategy_id": item.strategy_id,
                "strategy_version": item.strategy_version,
                "display_name": item.display_name,
                "parameter_schema_version": item.parameter_schema_version,
                "supported_directions": [direction.value for direction in item.supported_directions],
                "economic_scope": item.economic_scope,
            }
            for item in list_strategies()
        ]

    def strategy_schema(self, strategy_id: str) -> dict[str, Any]:
        return strategy_parameter_schema(strategy_id)

    def list_plans(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT d.plan_id, d.draft_version, d.content_digest, d.updated_at,
                       d.content, v.plan_version_id, v.fixed_at, v.content_digest
                FROM halpha.trade_plan_draft d
                LEFT JOIN LATERAL (
                    SELECT plan_version_id, fixed_at, content_digest
                    FROM halpha.trade_plan_version v
                    WHERE v.environment_id = d.environment_id AND v.plan_id = d.plan_id
                    ORDER BY fixed_at DESC LIMIT 1
                ) v ON true
                WHERE d.environment_id = %s
                ORDER BY d.updated_at DESC
                """,
                (self._environment_id,),
            ).fetchall()
        return [
            {
                "plan_id": str(row[0]),
                "draft_version": int(row[1]),
                "draft_content_digest": str(row[2]),
                "updated_at": row[3].isoformat(),
                "strategy_id": row[4]["strategy_id"],
                "instrument_ref": row[4]["instrument_ref"],
                "direction": row[4]["direction"],
                "plan_version_id": str(row[5]) if row[5] is not None else None,
                "fixed_at": row[6].isoformat() if row[6] is not None else None,
                "fixed_content_digest": str(row[7]) if row[7] is not None else None,
            }
            for row in rows
        ]

    def get_plan(self, plan_id: str) -> dict[str, Any]:
        with self._connect() as connection, connection.transaction():
            draft = PostgreSQLPlanningRepository(
                connection, self._environment_id
            ).get_draft(plan_id)
        return draft.model_dump(mode="json")

    def get_plan_version(self, plan_version_id: str) -> dict[str, Any]:
        with self._connect() as connection, connection.transaction():
            version = PostgreSQLPlanningRepository(
                connection, self._environment_id
            ).get_version(plan_version_id)
        return version.model_dump(mode="json")

    def save_new_plan(
        self,
        payload: PlanDraftPayload,
        *,
        idempotency_key: str,
        observed_at: datetime,
    ) -> dict[str, Any]:
        definition = describe_strategy(payload.strategy_id)
        if payload.direction not in {item.value for item in definition.supported_directions}:
            raise ValueError("PARAMETER_INVALID")
        parameters = {**payload.parameters, "direction": payload.direction}
        plan_id = _stable_id(self._environment_id, "plan", idempotency_key)
        content = TradePlanContent(
            strategy_id=payload.strategy_id,
            parameters=parameters,
            environment_id=self._environment_id,
            environment_kind=self._environment_kind,
            authority_class=self._authority_class,
            account_ref=self._account_ref,
            venue_ref=payload.venue_ref,
            instrument_ref=payload.instrument_ref,
            direction=payload.direction,
            target_exposure=payload.target_exposure,
            requested_limits=RequestedLimits(
                max_margin=payload.max_margin,
                max_notional=payload.max_notional,
                max_allowed_loss=payload.max_allowed_loss,
            ),
            valid_from=observed_at,
            valid_until=observed_at + timedelta(minutes=payload.valid_minutes),
            allowed_actions=definition.allowed_action_profiles,
            terms={
                "one_entry_cycle": True,
                "resume_policy": "MANUAL_PLAN_RESUME",
            },
        )
        with self._connect() as connection:
            repository = PostgreSQLPlanningRepository(connection, self._environment_id)
            service = PlanningApplicationService(connection, self._environment_id)
            try:
                with connection.transaction():
                    draft = service.create_draft(
                        plan_id=plan_id,
                        content=content,
                        observed_at=observed_at,
                    )
            except PlanningConflict:
                with connection.transaction():
                    draft = repository.get_draft(plan_id)
                if draft.content_digest != content_digest(content):
                    raise ValueError("IDEMPOTENCY_CONTENT_CONFLICT") from None
        return draft.model_dump(mode="json")

    def update_plan(
        self,
        plan_id: str,
        payload: PlanDraftPayload,
        *,
        expected_version: int,
        observed_at: datetime,
    ) -> dict[str, Any]:
        definition = describe_strategy(payload.strategy_id)
        content = TradePlanContent(
            strategy_id=payload.strategy_id,
            parameters={**payload.parameters, "direction": payload.direction},
            environment_id=self._environment_id,
            environment_kind=self._environment_kind,
            authority_class=self._authority_class,
            account_ref=self._account_ref,
            venue_ref=payload.venue_ref,
            instrument_ref=payload.instrument_ref,
            direction=payload.direction,
            target_exposure=payload.target_exposure,
            requested_limits=RequestedLimits(
                max_margin=payload.max_margin,
                max_notional=payload.max_notional,
                max_allowed_loss=payload.max_allowed_loss,
            ),
            valid_from=observed_at,
            valid_until=observed_at + timedelta(minutes=payload.valid_minutes),
            allowed_actions=definition.allowed_action_profiles,
            terms={"one_entry_cycle": True, "resume_policy": "MANUAL_PLAN_RESUME"},
        )
        with self._connect() as connection, connection.transaction():
            draft = PlanningApplicationService(connection, self._environment_id).update_draft(
                plan_id=plan_id,
                expected_version=expected_version,
                content=content,
                observed_at=observed_at,
            )
        return draft.model_dump(mode="json")

    def fix_plan(
        self,
        plan_id: str,
        *,
        idempotency_key: str,
        expected_version: int,
        observed_at: datetime,
    ) -> dict[str, Any]:
        if self._build_digest is None:
            raise ValueError("BUILD_MANIFEST_UNAVAILABLE")
        plan_version_id = _stable_id(self._environment_id, "plan-version", idempotency_key)
        gate_status = self._gate_status()
        with self._connect() as connection:
            repository = PostgreSQLPlanningRepository(connection, self._environment_id)
            try:
                with connection.transaction():
                    version = PlanningApplicationService(
                        connection, self._environment_id
                    ).fix_draft(
                        plan_id=plan_id,
                        expected_draft_version=expected_version,
                        plan_version_id=plan_version_id,
                        build_digest=self._build_digest,
                        evidence_digest=self._build_digest,
                        evidence_scope={
                            "construction_package": "B04",
                            "live_eligibility": (
                                gate_status.b05_package_eligibility == "AUTHORIZED"
                            ),
                            "runtime_real_write_gate": gate_status.runtime_real_write_gate,
                        },
                        fixed_at=observed_at,
                    )
            except psycopg.errors.UniqueViolation:
                connection.rollback()
                with connection.transaction():
                    version = repository.get_version(plan_version_id)
                if version.plan_id != plan_id:
                    raise ValueError("IDEMPOTENCY_CONTENT_CONFLICT") from None
        return version.model_dump(mode="json")

    def create_capital_limit(
        self,
        payload: CapitalLimitPayload,
        *,
        idempotency_key: str,
        observed_at: datetime,
    ) -> dict[str, Any]:
        limit_id = _stable_id(self._environment_id, "capital-limit", idempotency_key)
        fields = {
            "capital_limit_version_id": limit_id,
            "environment_id": self._environment_id,
            "environment_kind": self._environment_kind,
            "authority_class": self._authority_class,
            "account_ref": self._account_ref,
            "quote_asset": payload.quote_asset,
            "version": 1,
            "effective_at": observed_at,
            "max_margin": payload.max_margin,
            "max_notional": payload.max_notional,
            "max_allowed_loss": payload.max_allowed_loss,
            "max_action_notional": payload.max_action_notional,
            "scope": {"instruments": payload.instruments},
        }
        limit = AccountCapitalLimitVersion(**fields, content_digest=content_digest(fields))
        with self._connect() as connection:
            repository = PostgreSQLCapitalRepository(connection, self._environment_id)
            try:
                with connection.transaction():
                    repository.insert_account_limit(limit)
            except psycopg.errors.UniqueViolation:
                connection.rollback()
                with connection.transaction():
                    existing = repository.get_account_limit(limit_id)
                if existing.content_digest != limit.content_digest:
                    raise ValueError("IDEMPOTENCY_CONTENT_CONFLICT") from None
                limit = existing
        return limit.model_dump(mode="json")

    def capital_snapshot(self) -> dict[str, Any]:
        with self._connect() as connection:
            limits = connection.execute(
                """
                SELECT capital_limit_version_id, quote_asset, version, effective_at,
                       max_margin, max_notional, max_allowed_loss, max_action_notional,
                       scope, content_digest
                FROM halpha.account_capital_limit_version
                WHERE environment_id = %s AND account_ref = %s
                ORDER BY effective_at DESC
                """,
                (self._environment_id, self._account_ref),
            ).fetchall()
            allocations = connection.execute(
                """
                SELECT allocation_id, activation_id, quote_asset, max_margin,
                       max_notional, max_allowed_loss, status, state_version
                FROM halpha.plan_allocation
                WHERE environment_id = %s
                ORDER BY allocation_id
                """,
                (self._environment_id,),
            ).fetchall()
            authorizations = connection.execute(
                """
                SELECT authorization_version_id, activation_id, version,
                       valid_from, valid_until, action_profiles, content_digest
                FROM halpha.machine_authorization_version
                WHERE environment_id = %s
                ORDER BY valid_until DESC, authorization_version_id
                """,
                (self._environment_id,),
            ).fetchall()
            stops = connection.execute(
                """
                SELECT DISTINCT ON (
                    CASE WHEN activation_id IS NULL THEN 'ACCOUNT'
                         ELSE activation_id::text END
                ) stop_state_version_id, activation_id, version,
                  stopped_categories, reason, source, started_at, content_digest
                FROM halpha.stop_state_version
                WHERE environment_id = %s AND account_ref = %s
                ORDER BY CASE WHEN activation_id IS NULL THEN 'ACCOUNT'
                              ELSE activation_id::text END,
                         version DESC
                """,
                (self._environment_id, self._account_ref),
            ).fetchall()
        return {
            "environment_id": self._environment_id,
            "authority_class": self._authority_class.value,
            "account_ref": self._account_ref,
            "limits": [
                {
                    "capital_limit_version_id": str(row[0]),
                    "quote_asset": str(row[1]),
                    "version": int(row[2]),
                    "effective_at": row[3].isoformat(),
                    "max_margin": str(row[4]),
                    "max_notional": str(row[5]),
                    "max_allowed_loss": str(row[6]),
                    "max_action_notional": str(row[7]),
                    "scope": dict(row[8]),
                    "content_digest": str(row[9]),
                }
                for row in limits
            ],
            "allocations": [
                {
                    "allocation_id": str(row[0]),
                    "activation_id": str(row[1]),
                    "quote_asset": str(row[2]),
                    "max_margin": str(row[3]),
                    "max_notional": str(row[4]),
                    "max_allowed_loss": str(row[5]),
                    "status": str(row[6]),
                    "state_version": int(row[7]),
                }
                for row in allocations
            ],
            "authorizations": [
                {
                    "authorization_version_id": str(row[0]),
                    "activation_id": str(row[1]),
                    "version": int(row[2]),
                    "valid_from": row[3].isoformat(),
                    "valid_until": row[4].isoformat(),
                    "action_profiles": list(row[5]),
                    "content_digest": str(row[6]),
                }
                for row in authorizations
            ],
            "stops": [
                {
                    "stop_state_version_id": str(row[0]),
                    "activation_id": str(row[1]) if row[1] is not None else None,
                    "version": int(row[2]),
                    "stopped_categories": list(row[3]),
                    "reason": str(row[4]),
                    "source": str(row[5]),
                    "started_at": row[6].isoformat(),
                    "content_digest": str(row[7]),
                }
                for row in stops
            ],
        }

    def activation_preview(self, plan_version_id: str) -> dict[str, Any]:
        with self._connect() as connection, connection.transaction():
            version = PostgreSQLPlanningRepository(
                connection, self._environment_id
            ).get_version(plan_version_id)
        gate_status = self._gate_status()
        return {
            "plan_version_id": version.plan_version_id,
            "environment_id": self._environment_id,
            "environment_kind": self._environment_kind.value,
            "authority_class": self._authority_class.value,
            "account_ref": version.account_ref,
            "instrument_ref": version.instrument_ref,
            "direction": version.direction.value,
            "strategy_ref": (
                f"{version.strategy_basis.strategy_id}@{version.strategy_basis.strategy_version}"
            ),
            "parameter_digest": version.strategy_basis.parameter_digest,
            "limits": version.requested_limits.model_dump(mode="json"),
            "valid_until": version.valid_until.isoformat(),
            "allowed_actions": sorted(version.allowed_actions),
            "actual_account_configuration": "B03_PRE_SUBMIT_FACT_NOT_REQUIRED_FOR_P0_ACTIVATION",
            "account_mode_policy": "USE_ACTUAL_CONFIGURATION_WITH_EFFECTIVE_LEVERAGE_MIN_ACTUAL_5",
            "live_write_build_capability": gate_status.live_write_build_capability,
            "b05_package_eligibility": gate_status.b05_package_eligibility,
            "configured_runtime_real_write_gate": (
                gate_status.configured_runtime_real_write_gate
            ),
            "runtime_real_write_gate": gate_status.runtime_real_write_gate,
            "live_activation_eligible": (
                self._profile == "BINANCE_LIVE_WRITE"
                and gate_status.live_write_build_capability == "QUALIFIED"
                and gate_status.b05_package_eligibility == "AUTHORIZED"
                and gate_status.configured_runtime_real_write_gate == "CLOSED"
            ),
            "capital_notice": "Halpha 内部互斥额度，不是 Binance 资金冻结或损失保证。",
        }

    def activate(
        self,
        payload: ActivationPayload,
        *,
        idempotency_key: str,
        observed_at: datetime,
    ) -> dict[str, Any]:
        gate_status = self._gate_status()
        activation_terms: dict[str, bool] = {}
        if self._profile == "BINANCE_LIVE_READ_ONLY":
            raise ValueError("LIVE_READ_ONLY_ACTIVATION_FORBIDDEN")
        if self._profile == "BINANCE_LIVE_WRITE":
            if gate_status.live_write_build_capability != "QUALIFIED":
                raise ValueError("LIVE_WRITE_BUILD_CAPABILITY_NOT_QUALIFIED")
            if gate_status.b05_package_eligibility != "AUTHORIZED":
                raise ValueError("B05_PACKAGE_NOT_AUTHORIZED")
            if gate_status.configured_runtime_real_write_gate != "CLOSED":
                raise ValueError("LIVE_WRITE_GATE_MUST_BE_CLOSED_FOR_ACTIVATION")
            activation_terms = {
                "real_capital_acknowledged": payload.real_capital_acknowledged,
                "evidence_limitations_acknowledged": (
                    payload.evidence_limitations_acknowledged
                ),
                "online_monitoring_acknowledged": (
                    payload.online_monitoring_acknowledged
                ),
            }
            if any(value is not True for value in activation_terms.values()):
                raise ValueError("LIVE_OWNER_ACKNOWLEDGEMENTS_REQUIRED")
        activation_id = _stable_id(self._environment_id, "activation", idempotency_key)
        authorization_id = _stable_id(self._environment_id, "authorization", idempotency_key)
        allocation_id = _stable_id(self._environment_id, "allocation", idempotency_key)
        with self._connect() as connection:
            planning = PostgreSQLPlanningRepository(connection, self._environment_id)
            try:
                with connection.transaction():
                    activation, authorization, allocation = PlanningApplicationService(
                        connection, self._environment_id
                    ).activate_version(
                        plan_version_id=payload.plan_version_id,
                        activation_id=activation_id,
                        authorization_version_id=authorization_id,
                        allocation_id=allocation_id,
                        capital_limit_version_id=payload.capital_limit_version_id,
                        quote_asset=payload.quote_asset,
                        observed_at=observed_at,
                        activation_terms=activation_terms,
                    )
            except psycopg.errors.UniqueViolation as exc:
                constraint_name = exc.diag.constraint_name
                connection.rollback()
                with connection.transaction():
                    try:
                        activation = planning.get_activation(activation_id)
                    except PlanningConflict:
                        if constraint_name == "uq_plan_activation_open_scope":
                            raise ValueError("ATTRIBUTION_AMBIGUOUS") from None
                        raise ValueError("IDEMPOTENCY_CONTENT_CONFLICT") from None
                    allocation = PostgreSQLCapitalRepository(
                        connection, self._environment_id
                    ).get_allocation(activation_id)
                if (
                    activation.plan_version_ref != payload.plan_version_id
                    or activation.authorization_version_ref != authorization_id
                    or activation.allocation_ref != allocation_id
                    or allocation.allocation_id != allocation_id
                    or allocation.capital_limit_version_ref
                    != payload.capital_limit_version_id
                    or allocation.quote_asset != payload.quote_asset
                ):
                    raise ValueError("IDEMPOTENCY_CONTENT_CONFLICT") from None
                authorization = None
        return {
            "activation": activation.model_dump(mode="json"),
            "authorization_version_id": (
                authorization.authorization_version_id if authorization else authorization_id
            ),
            "allocation": allocation.model_dump(mode="json"),
            "venue_write_created": False,
            "runtime_real_write_gate": self._gate_status().runtime_real_write_gate,
        }

    def list_activations(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT activation_id FROM halpha.plan_activation
                WHERE environment_id = %s ORDER BY created_at DESC
                """,
                (self._environment_id,),
            ).fetchall()
            repository = PostgreSQLPlanningRepository(connection, self._environment_id)
            return [
                repository.get_activation(str(row[0])).model_dump(mode="json")
                for row in rows
            ]

    def activation_detail(self, activation_id: str) -> dict[str, Any]:
        with self._connect() as connection, connection.transaction():
            activation = PostgreSQLPlanningRepository(
                connection, self._environment_id
            ).get_activation(activation_id)
            allocation = PostgreSQLCapitalRepository(
                connection, self._environment_id
            ).get_allocation(activation_id)
            actions = connection.execute(
                """
                SELECT execution_action_id, action_kind, action_class, action_terms,
                       client_order_id, state, state_version, unknown_reason,
                       protection_digest, closure_evidence_digest, created_at, updated_at,
                       execution_profile_ref, account_ref, authority_class
                FROM halpha.execution_action
                WHERE environment_id = %s AND activation_id = %s
                ORDER BY created_at, execution_action_id
                """,
                (self._environment_id, activation_id),
            ).fetchall()
            facts = connection.execute(
                """
                SELECT venue_fact_id, kind, source_class, source_object_id,
                       source_time, received_at, cutoff, payload, action_ref,
                       attribution_class, content_digest
                FROM halpha.venue_fact
                WHERE environment_id = %s AND activation_ref = %s
                ORDER BY cutoff, venue_fact_id
                """,
                (self._environment_id, activation_id),
            ).fetchall()
            receipts = connection.execute(
                """
                SELECT c.command_id, c.intent, c.submitted_at, r.receipt_id,
                       r.state, r.state_version, r.reason_code, r.updated_at
                FROM halpha.command c
                JOIN halpha.receipt r
                  ON r.environment_id = c.environment_id AND r.command_id = c.command_id
                WHERE c.environment_id = %s AND c.target_kind = 'PLAN_ACTIVATION'
                  AND c.target_ref = %s
                ORDER BY c.submitted_at, c.command_id
                """,
                (self._environment_id, activation_id),
            ).fetchall()
            stops = connection.execute(
                """
                SELECT stopped_categories, reason, source, started_at, version
                FROM (
                  SELECT DISTINCT ON (
                    CASE WHEN activation_id IS NULL THEN 'ACCOUNT'
                         ELSE activation_id::text END
                  ) activation_id, stopped_categories, reason, source, started_at, version
                  FROM halpha.stop_state_version
                  WHERE environment_id = %s AND account_ref = %s
                    AND (activation_id IS NULL OR activation_id = %s)
                  ORDER BY CASE WHEN activation_id IS NULL THEN 'ACCOUNT'
                                ELSE activation_id::text END,
                           version DESC
                ) current_stops
                """,
                (self._environment_id, self._account_ref, activation_id),
            ).fetchall()
        stopped_categories = {
            str(category) for row in stops for category in row[0]
        }
        if "ALL_WRITES" in stopped_categories:
            stopped_categories.update(
                {
                    "NEW_FUNDING",
                    "PROTECTION",
                    "RISK_REDUCTION_OR_ORDER_MANAGEMENT",
                }
            )
        return {
            "activation": activation.model_dump(mode="json"),
            "allocation": allocation.model_dump(mode="json"),
            "execution_actions": [
                {
                    "execution_action_id": str(row[0]),
                    "action_kind": str(row[1]),
                    "action_class": str(row[2]),
                    "action_terms": dict(row[3]),
                    "client_order_id": str(row[4]) if row[4] is not None else None,
                    "state": str(row[5]),
                    "state_version": int(row[6]),
                    "unknown_reason": str(row[7]) if row[7] is not None else None,
                    "protection_digest": str(row[8]) if row[8] is not None else None,
                    "closure_evidence_digest": str(row[9]) if row[9] is not None else None,
                    "created_at": row[10].isoformat(),
                    "updated_at": row[11].isoformat(),
                    "execution_profile_ref": str(row[12]),
                    "account_ref": str(row[13]),
                    "authority_class": str(row[14]),
                }
                for row in actions
            ],
            "venue_facts": [
                {
                    "venue_fact_id": str(row[0]),
                    "kind": str(row[1]),
                    "source_class": str(row[2]),
                    "source_object_id": str(row[3]) if row[3] is not None else None,
                    "source_time": row[4].isoformat() if row[4] is not None else None,
                    "received_at": row[5].isoformat(),
                    "cutoff": row[6].isoformat(),
                    "payload": dict(row[7]),
                    "action_ref": str(row[8]) if row[8] is not None else None,
                    "attribution_class": str(row[9]) if row[9] is not None else None,
                    "content_digest": str(row[10]),
                }
                for row in facts
            ],
            "receipts": [
                {
                    "command_id": str(row[0]),
                    "intent": str(row[1]),
                    "submitted_at": row[2].isoformat(),
                    "receipt_id": str(row[3]),
                    "state": str(row[4]),
                    "state_version": int(row[5]),
                    "reason_code": str(row[6]) if row[6] is not None else None,
                    "updated_at": row[7].isoformat(),
                }
                for row in receipts
            ],
            "stopped_categories": sorted(stopped_categories),
            "stop_evidence": [
                {
                    "categories": list(row[0]),
                    "reason": str(row[1]),
                    "source": str(row[2]),
                    "started_at": row[3].isoformat(),
                    "version": int(row[4]),
                }
                for row in stops
            ],
            "runtime_real_write_gate": self._gate_status().runtime_real_write_gate,
        }

    def activation_timeline(self, activation_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            event_rows = connection.execute(
                """
                SELECT plan_event_id, rule_id, source_identity, source_cutoff,
                       reason_code, no_action_reason, capital_decision, created_at
                FROM halpha.plan_event
                WHERE environment_id = %s AND activation_id = %s
                ORDER BY created_at, plan_event_id
                """,
                (self._environment_id, activation_id),
            ).fetchall()
            action_rows = connection.execute(
                """
                SELECT execution_action_id, action_kind, state, state_version,
                       client_order_id, unknown_reason, created_at, updated_at,
                       execution_profile_ref, account_ref, authority_class
                FROM halpha.execution_action
                WHERE environment_id = %s AND activation_id = %s
                ORDER BY created_at, execution_action_id
                """,
                (self._environment_id, activation_id),
            ).fetchall()
            fact_rows = connection.execute(
                """
                SELECT venue_fact_id, kind, source_class, source_object_id,
                       action_ref, cutoff, content_digest
                FROM halpha.venue_fact
                WHERE environment_id = %s AND activation_ref = %s
                ORDER BY cutoff, venue_fact_id
                """,
                (self._environment_id, activation_id),
            ).fetchall()
        timeline = [
            {
                "source": "PLAN_EVENT",
                "source_ref": str(row[0]),
                "stage_order": 1,
                "at": row[7].isoformat(),
                "status": str(row[4]),
                "detail": {
                    "rule_id": str(row[1]),
                    "source_identity": str(row[2]),
                    "source_cutoff": row[3].isoformat(),
                    "no_action_reason": str(row[5]) if row[5] is not None else None,
                    "capital_decision": dict(row[6]),
                },
            }
            for row in event_rows
        ]
        timeline.extend(
            {
                "source": "EXECUTION_ACTION",
                "source_ref": str(row[0]),
                "stage_order": 2,
                "at": row[7].isoformat(),
                "status": str(row[2]),
                "detail": {
                    "action_kind": str(row[1]),
                    "state_version": int(row[3]),
                    "client_order_id": str(row[4]) if row[4] is not None else None,
                    "unknown_reason": str(row[5]) if row[5] is not None else None,
                    "created_at": row[6].isoformat(),
                    "environment_id": self._environment_id,
                    "execution_profile_ref": str(row[8]),
                    "account_ref": str(row[9]),
                    "authority_class": str(row[10]),
                },
            }
            for row in action_rows
        )
        timeline.extend(
            {
                "source": "VENUE_FACT",
                "source_ref": str(row[0]),
                "stage_order": 3,
                "at": row[5].isoformat(),
                "status": str(row[1]),
                "detail": {
                    "source_class": str(row[2]),
                    "source_object_id": str(row[3]) if row[3] is not None else None,
                    "action_ref": str(row[4]) if row[4] is not None else None,
                    "content_digest": str(row[6]),
                },
            }
            for row in fact_rows
        )
        return sorted(
            timeline,
            key=lambda item: (item["at"], item["stage_order"], item["source_ref"]),
        )

    def control_preview(self, activation_id: str, intent: ControlIntent) -> dict[str, Any]:
        current = self.activation_detail(activation_id)
        consequences = {
            ControlIntent.STOP_NEW_RISK: "立即阻止新风险；已有查询、保护、撤单和减险责任继续。",
            ControlIntent.RESUME_NEW_RISK: "仅解除可恢复的用户停增险；不解除最大损失、退出、接管或 ALL_WRITES。",
            ControlIntent.RESUME_ACTIVATION: "仅解除 WRITER_CONTINUITY_LOST 暂停；当前授权、事实和安全停止仍需通过。",
            ControlIntent.EXIT_STRATEGY: "进入 EXITING，停止增险并等待 B03 执行与闭合责任。",
            ControlIntent.USER_TAKEOVER: "先持久化责任转移，再停止自动写；不会自动撤单或平仓。",
        }
        activation = current["activation"]
        allocation = current["allocation"]
        preview_basis = {
            "activation_id": activation_id,
            "intent": intent.value,
            "activation_state_version": activation["state_version"],
            "lifecycle": activation["lifecycle"],
            "run_state": activation["run_state"],
            "pause_reason": activation["pause_reason"],
            "protection_state": activation["protection_state"],
            "allocation_state_version": allocation["state_version"],
            "allocation_status": allocation["status"],
            "max_loss_reached": allocation["max_loss_reached"],
        }
        return {
            **current,
            "intent": intent.value,
            "consequence": consequences[intent],
            "preview_digest": content_digest(preview_basis),
            "previewed_at": datetime.now(UTC).isoformat(),
            "resume_eligible": False if intent is ControlIntent.RESUME_ACTIVATION else None,
            "resume_denial_reasons": (
                ["B03_AUTHORITATIVE_RECONCILIATION_NOT_AVAILABLE"]
                if intent is ControlIntent.RESUME_ACTIVATION
                else []
            ),
            "reconciliation_digest": None,
            "venue_write_created_by_preview": False,
        }

    def submit_control(
        self,
        activation_id: str,
        intent: ControlIntent,
        payload: ControlPayload,
        *,
        idempotency_key: str,
        observed_at: datetime,
    ) -> dict[str, Any]:
        command_id = _stable_id(self._environment_id, "command", idempotency_key)
        receipt_id = _stable_id(self._environment_id, "receipt", idempotency_key)
        stop_id = _stable_id(self._environment_id, "stop-state", idempotency_key)
        scope = {
            "activation_id": activation_id,
            "cutoff": observed_at.isoformat(),
            **payload.takeover_scope,
        }
        command = build_command(
            command_id=command_id,
            environment_id=self._environment_id,
            owner_scope="local-owner",
            idempotency_key=idempotency_key,
            activation_id=activation_id,
            expected_version=payload.expected_version,
            intent=intent,
            scope=scope,
            parameters={},
            submitted_at=observed_at,
        )
        with self._connect() as connection, connection.transaction():
            receipt = ActivationControlService(connection, self._environment_id).submit(
                command,
                receipt_id=receipt_id,
                stop_state_version_id=stop_id,
                # User input is never trusted as reconciliation evidence. B03 will
                # inject evidence produced by the unique Executor/EXE path.
                reconciliation_digest=None,
            )
        return receipt.model_dump(mode="json")

    def receipt(self, receipt_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT receipt_id, command_id, processing_owner, state, state_version,
                       reason_code, result, pending_responsibility_refs,
                       content_digest, created_at, updated_at
                FROM halpha.receipt
                WHERE environment_id = %s AND receipt_id = %s
                """,
                (self._environment_id, receipt_id),
            ).fetchone()
        if row is None:
            raise ValueError("RECEIPT_NOT_FOUND")
        return {
            "receipt_id": str(row[0]),
            "command_id": str(row[1]),
            "processing_owner": str(row[2]),
            "state": str(row[3]),
            "state_version": int(row[4]),
            "reason_code": str(row[5]) if row[5] is not None else None,
            "result": dict(row[6]) if row[6] is not None else None,
            "pending_responsibility_refs": list(row[7]),
            "content_digest": str(row[8]),
            "created_at": row[9].isoformat(),
            "updated_at": row[10].isoformat(),
        }

    def list_tasks(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT task_id, responsibility_key, priority, due_at, source_kind,
                       source_ref, source_version, source_digest, state, state_version,
                       resolution_ref, content_digest, created_at, updated_at
                FROM halpha.task
                WHERE environment_id = %s
                ORDER BY
                  CASE priority WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2
                                WHEN 'NORMAL' THEN 3 ELSE 4 END,
                  due_at NULLS LAST, created_at, task_id
                """,
                (self._environment_id,),
            ).fetchall()
        return [
            {
                "task_id": str(row[0]),
                "responsibility_key": str(row[1]),
                "priority": str(row[2]),
                "due_at": row[3].isoformat() if row[3] is not None else None,
                "source_kind": str(row[4]),
                "source_ref": str(row[5]),
                "source_version": int(row[6]),
                "source_digest": str(row[7]),
                "state": str(row[8]),
                "state_version": int(row[9]),
                "resolution_ref": str(row[10]) if row[10] is not None else None,
                "content_digest": str(row[11]),
                "created_at": row[12].isoformat(),
                "updated_at": row[13].isoformat(),
            }
            for row in rows
        ]

    def acknowledge_task(
        self,
        task_id: str,
        *,
        expected_version: int,
        observed_at: datetime,
    ) -> dict[str, Any]:
        with self._connect() as connection, connection.transaction():
            row = connection.execute(
                """
                SELECT task_id, environment_id, owner_scope, responsibility_key,
                       priority, due_at, source_kind, source_ref, source_version,
                       source_digest, state, state_version, resolution_ref,
                       created_at, updated_at
                FROM halpha.task
                WHERE environment_id = %s AND task_id = %s
                FOR UPDATE
                """,
                (self._environment_id, task_id),
            ).fetchone()
            if row is None:
                raise ValueError("TASK_NOT_FOUND")
            if int(row[11]) != expected_version:
                raise ValueError("VERSION_CONFLICT")
            if str(row[10]) == "RESOLVED":
                raise ValueError("TASK_ALREADY_RESOLVED")
            next_version = expected_version + 1
            fields = {
                "task_id": str(row[0]),
                "environment_id": str(row[1]),
                "owner_scope": str(row[2]),
                "responsibility_key": str(row[3]),
                "priority": str(row[4]),
                "due_at": row[5],
                "source_kind": str(row[6]),
                "source_ref": str(row[7]),
                "source_version": int(row[8]),
                "source_digest": str(row[9]),
                "state": "ACKNOWLEDGED",
                "state_version": next_version,
                "resolution_ref": str(row[12]) if row[12] is not None else None,
                "created_at": row[14],
                "updated_at": observed_at,
            }
            digest = content_digest(fields)
            cursor = connection.execute(
                """
                UPDATE halpha.task
                SET state = 'ACKNOWLEDGED', state_version = %s,
                    content_digest = %s, updated_at = %s
                WHERE environment_id = %s AND task_id = %s AND state_version = %s
                """,
                (
                    next_version,
                    digest,
                    observed_at,
                    self._environment_id,
                    task_id,
                    expected_version,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("VERSION_CONFLICT")
        return {
            "task_id": task_id,
            "state": "ACKNOWLEDGED",
            "state_version": next_version,
            "content_digest": digest,
            "source_responsibility_changed": False,
            "updated_at": observed_at.isoformat(),
        }
