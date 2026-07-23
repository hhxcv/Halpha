"""App boundary for plans and activation transactions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import psycopg
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from halpha.capital.models import (
    AuthorityClass,
    EnvironmentKind,
)
from halpha.domain_values import canonical_decimal, content_digest, decimal_from_string
from halpha.live_write_gate import (
    GateStatusProvider,
    LiveWriteGateStatus,
    closed_live_write_gate_status,
)
from halpha.outcomes.trade_result import summarize_trade_result
from halpha.planning.models import (
    PlanCreatorKind,
    PlanLifecycle,
    RequestedLimits,
    TradePlanContent,
)
from halpha.planning.order_schedule import (
    OrderSchedulePreview,
    OrderScheduleSpec,
    direct_allowed_action_profiles,
    validate_current_order_schedule_support,
)
from halpha.planning.control_service import ActivationControlService
from halpha.planning.registry import (
    DecisionBasisKind,
    DraftDecisionBasis,
    FixedStrategyPlanBasis,
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
    plan_name: str
    decision_basis: DraftDecisionBasis | None = None
    order_schedule_spec: OrderScheduleSpec | None = None
    strategy_id: str | None = None
    parameters: dict[str, Any] | None = None
    venue_ref: str = "BINANCE_USDM"
    instrument_ref: str
    direction: str
    target_exposure: str
    max_margin: str
    max_notional: str
    max_allowed_loss: str
    valid_minutes: int = Field(ge=15, le=10080)

    @field_validator("plan_name")
    @classmethod
    def readable_plan_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 80:
            raise ValueError("PLAN_NAME_INVALID")
        return normalized

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

    @model_validator(mode="after")
    def decision_basis_is_unambiguous(self) -> PlanDraftPayload:
        has_legacy = self.strategy_id is not None or self.parameters is not None
        if self.decision_basis is not None and has_legacy:
            raise ValueError("DECISION_BASIS_AMBIGUOUS")
        if self.decision_basis is None:
            if self.strategy_id is None or self.parameters is None:
                raise ValueError("DECISION_BASIS_REQUIRED")
            basis_kind = DecisionBasisKind.STRATEGY_SIGNAL
        else:
            basis_kind = self.decision_basis.kind
        validate_current_order_schedule_support(
            basis_kind,
            self.order_schedule_spec,
        )
        return self

    def resolved_decision_basis(self) -> DraftDecisionBasis:
        if self.decision_basis is not None:
            basis = self.decision_basis
        else:
            basis = DraftDecisionBasis(
                kind=DecisionBasisKind.STRATEGY_SIGNAL,
                decision_basis_ref=str(self.strategy_id),
                parameters=dict(self.parameters or {}),
            )
        if basis.kind is DecisionBasisKind.STRATEGY_SIGNAL:
            return basis.model_copy(
                update={"parameters": {**basis.parameters, "direction": self.direction}}
            )
        return basis


class PlanCreatePayload(PlanDraftPayload):
    creator_kind: PlanCreatorKind


class ActivationPayload(ApiModel):
    plan_version_id: str
    expected_schedule_digest: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )


class ControlPayload(ApiModel):
    expected_version: int = Field(gt=0)
    takeover_scope: dict[str, Any] = Field(default_factory=dict)


class PlanningApiUnavailable(RuntimeError):
    pass


def _stable_id(environment_id: str, kind: str, idempotency_key: str) -> str:
    return str(
        uuid5(NAMESPACE_URL, f"urn:halpha:{environment_id}:{kind}:{idempotency_key}")
    )


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _iso_value(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _fixed_decision_basis_projection(version: Any) -> dict[str, Any]:
    basis = getattr(version, "decision_basis", None)
    if basis is None:
        basis = version.strategy_basis
    kind = str(
        _enum_value(getattr(basis, "kind", DecisionBasisKind.STRATEGY_SIGNAL))
    )
    decision_basis_ref = getattr(basis, "decision_basis_ref", None)
    if decision_basis_ref is None:
        decision_basis_ref = (
            f"{basis.strategy_id}@{basis.strategy_version}"
            if kind == DecisionBasisKind.STRATEGY_SIGNAL.value
            else str(getattr(basis, "strategy_id", ""))
        )
    if hasattr(basis, "model_dump"):
        payload = basis.model_dump(mode="json")
    else:
        payload = {
            key: _enum_value(value)
            for key, value in vars(basis).items()
        }
    payload["kind"] = kind
    payload["decision_basis_ref"] = str(decision_basis_ref)
    return {
        "model": basis,
        "payload": payload,
        "kind": kind,
        "decision_basis_ref": str(decision_basis_ref),
        "parameter_digest": str(basis.parameter_digest),
        "normalized_parameters": dict(basis.normalized_parameters),
        "product_build_id": str(basis.product_build_id),
        "legacy_unverified": bool(getattr(basis, "legacy_unverified", False)),
    }


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
        product_build_id: str,
        profile: str | None = None,
        gate_status_provider: GateStatusProvider | None = None,
    ) -> None:
        self._database_name = database_name
        self._password = password
        self._environment_id = environment_id
        self._environment_kind = EnvironmentKind(environment_kind)
        self._authority_class = AuthorityClass(authority_class)
        self._account_ref = account_ref
        self._product_build_id = product_build_id
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

    def _require_demo_parameter_scope(self, parameters: dict[str, Any]) -> None:
        if (
            parameters.get("demo_immediate_entry") is True
            and self._profile != "BINANCE_DEMO"
        ):
            raise ValueError("DEMO_IMMEDIATE_ENTRY_REQUIRES_DEMO")

    def strategies(self) -> list[dict[str, Any]]:
        return [
            {
                "strategy_id": item.strategy_id,
                "strategy_version": item.strategy_version,
                "display_name": item.display_name,
                "value_logic": item.value_logic,
                "applicable_scenarios": item.applicable_scenarios,
                "execution_behavior": item.execution_behavior,
                "parameter_schema_version": item.parameter_schema_version,
                "supported_directions": [
                    direction.value for direction in item.supported_directions
                ],
                "economic_scope": item.economic_scope,
                "plan_key_parameters": [
                    parameter.model_dump(mode="json")
                    for parameter in item.plan_key_parameters
                ],
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
                       d.content, v.plan_version_id, v.fixed_at, v.content_digest,
                       v.product_build_id, v.terms ->> 'valid_until'
                FROM halpha.trade_plan_draft d
                LEFT JOIN LATERAL (
                    SELECT plan_version_id, fixed_at, content_digest,
                           product_build_id, terms
                    FROM halpha.trade_plan_version v
                    WHERE v.environment_id = d.environment_id AND v.plan_id = d.plan_id
                    ORDER BY fixed_at DESC LIMIT 1
                ) v ON true
                WHERE d.environment_id = %s
                ORDER BY d.updated_at DESC
                """,
                (self._environment_id,),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            content = dict(row[4])
            basis = DraftDecisionBasis.model_validate(
                content.get("decision_basis")
                or {
                    "kind": DecisionBasisKind.STRATEGY_SIGNAL.value,
                    "decision_basis_ref": content["strategy_id"],
                    "parameters": content["parameters"],
                }
            )
            requested_limits = dict(content["requested_limits"])
            result.append(
                {
                "plan_id": str(row[0]),
                "draft_version": int(row[1]),
                "draft_content_digest": str(row[2]),
                "updated_at": row[3].isoformat(),
                "plan_name": content.get("plan_name"),
                "created_at": _iso_value(content.get("created_at")),
                "creator_kind": _enum_value(content.get("creator_kind")),
                "decision_basis": basis.model_dump(mode="json"),
                "decision_basis_kind": basis.kind.value,
                "decision_basis_ref": basis.decision_basis_ref,
                "strategy_id": (
                    basis.decision_basis_ref
                    if basis.kind is DecisionBasisKind.STRATEGY_SIGNAL
                    else None
                ),
                "instrument_ref": str(content["instrument_ref"]),
                "direction": str(_enum_value(content["direction"])),
                "parameters": dict(basis.parameters),
                "order_schedule_spec": content.get("order_schedule_spec"),
                "max_notional": str(requested_limits["max_notional"]),
                "valid_from": _iso_value(content["valid_from"]),
                "valid_until": _iso_value(content["valid_until"]),
                "plan_version_id": str(row[5]) if row[5] is not None else None,
                "fixed_at": row[6].isoformat() if row[6] is not None else None,
                "fixed_content_digest": str(row[7]) if row[7] is not None else None,
                "fixed_product_build_id": str(row[8]) if row[8] is not None else None,
                "fixed_valid_until": str(row[9]) if row[9] is not None else None,
                "product_build_consistent": (
                    str(row[8]) == self._product_build_id
                    if row[8] is not None
                    else None
                ),
                }
            )
        return result

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
        payload: PlanCreatePayload,
        *,
        idempotency_key: str,
        observed_at: datetime,
    ) -> dict[str, Any]:
        basis = payload.resolved_decision_basis()
        if basis.kind is DecisionBasisKind.STRATEGY_SIGNAL:
            definition = describe_strategy(basis.decision_basis_ref)
            if payload.direction not in {
                item.value for item in definition.supported_directions
            }:
                raise ValueError("PARAMETER_INVALID")
            allowed_actions = frozenset(
                definition.allowed_action_profiles
            )
            self._require_demo_parameter_scope(basis.parameters)
        else:
            allowed_actions = direct_allowed_action_profiles(
                payload.order_schedule_spec
            )
        plan_id = _stable_id(self._environment_id, "plan", idempotency_key)
        content = TradePlanContent(
            plan_name=payload.plan_name,
            created_at=observed_at,
            creator_kind=payload.creator_kind,
            decision_basis=basis,
            order_schedule_spec=payload.order_schedule_spec,
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
            allowed_actions=allowed_actions,
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
                request_duration = content.valid_until - content.valid_from
                comparable = content.model_copy(
                    update={
                        "created_at": draft.content.created_at,
                        "valid_from": draft.content.valid_from,
                        "valid_until": draft.content.valid_from + request_duration,
                    }
                )
                if content_digest(draft.content) != content_digest(comparable):
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
        basis = payload.resolved_decision_basis()
        if basis.kind is DecisionBasisKind.STRATEGY_SIGNAL:
            definition = describe_strategy(basis.decision_basis_ref)
            if payload.direction not in {
                item.value for item in definition.supported_directions
            }:
                raise ValueError("PARAMETER_INVALID")
            allowed_actions = frozenset(
                definition.allowed_action_profiles
            )
            self._require_demo_parameter_scope(basis.parameters)
        else:
            allowed_actions = direct_allowed_action_profiles(
                payload.order_schedule_spec
            )
        content = TradePlanContent(
            plan_name=payload.plan_name,
            decision_basis=basis,
            order_schedule_spec=payload.order_schedule_spec,
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
            allowed_actions=allowed_actions,
            terms={"one_entry_cycle": True, "resume_policy": "MANUAL_PLAN_RESUME"},
        )
        with self._connect() as connection, connection.transaction():
            draft = PlanningApplicationService(
                connection, self._environment_id
            ).update_draft(
                plan_id=plan_id,
                expected_version=expected_version,
                content=content,
                observed_at=observed_at,
            )
        return draft.model_dump(mode="json")

    def delete_plan(self, plan_id: str, *, expected_version: int) -> dict[str, Any]:
        with self._connect() as connection, connection.transaction():
            PlanningApplicationService(
                connection, self._environment_id
            ).delete_draft(
                plan_id=plan_id,
                expected_version=expected_version,
            )
        return {
            "result": "APPLIED",
            "plan_id": plan_id,
            "deleted_draft_version": expected_version,
        }

    def fix_plan(
        self,
        plan_id: str,
        *,
        idempotency_key: str,
        expected_version: int,
        observed_at: datetime,
    ) -> dict[str, Any]:
        plan_version_id = _stable_id(
            self._environment_id, "plan-version", idempotency_key
        )
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
                        product_build_id=self._product_build_id,
                        fixed_at=observed_at,
                    )
            except psycopg.errors.UniqueViolation:
                connection.rollback()
                with connection.transaction():
                    version = repository.get_version(plan_version_id)
                if version.plan_id != plan_id:
                    raise ValueError("IDEMPOTENCY_CONTENT_CONFLICT") from None
        return version.model_dump(mode="json")

    def activation_preview(self, plan_version_id: str) -> dict[str, Any]:
        with self._connect() as connection, connection.transaction():
            version = PostgreSQLPlanningRepository(
                connection, self._environment_id
            ).get_version(plan_version_id)
        basis = _fixed_decision_basis_projection(version)
        gate_status = self._gate_status()
        product_build_consistent = (
            not basis["legacy_unverified"]
            and basis["product_build_id"] == self._product_build_id
            and (
                self._profile != "BINANCE_LIVE_WRITE"
                or gate_status.product_build_consistent is True
            )
        )
        return {
            "plan_version_id": version.plan_version_id,
            "plan_name": version.plan_name,
            "created_at": (
                version.created_at.isoformat() if version.created_at is not None else None
            ),
            "creator_kind": (
                version.creator_kind.value if version.creator_kind is not None else None
            ),
            "environment_id": self._environment_id,
            "environment_kind": self._environment_kind.value,
            "authority_class": self._authority_class.value,
            "account_ref": version.account_ref,
            "venue_ref": getattr(version, "venue_ref", "BINANCE_USDM"),
            "instrument_ref": version.instrument_ref,
            "direction": version.direction.value,
            "decision_basis": basis["payload"],
            "decision_basis_kind": basis["kind"],
            "decision_basis_ref": basis["decision_basis_ref"],
            "strategy_ref": (
                basis["decision_basis_ref"]
                if basis["kind"] == DecisionBasisKind.STRATEGY_SIGNAL.value
                else None
            ),
            "parameter_digest": basis["parameter_digest"],
            "strategy_parameters": basis["normalized_parameters"],
            "order_schedule_spec": (
                version.order_schedule_spec.model_dump(mode="json")
                if getattr(version, "order_schedule_spec", None) is not None
                else None
            ),
            "trade_amount": version.requested_limits.max_notional,
            "limits": version.requested_limits.model_dump(mode="json"),
            "valid_until": version.valid_until.isoformat(),
            "allowed_actions": sorted(version.allowed_actions),
            "actual_account_configuration": "PRE_SUBMIT_FACT_NOT_REQUIRED_FOR_PLAN_ACTIVATION",
            "account_mode_policy": "USE_ACTUAL_CONFIGURATION_WITH_EFFECTIVE_LEVERAGE_MIN_ACTUAL_5",
            "product_build_id": basis["product_build_id"],
            "legacy_unverified": basis["legacy_unverified"],
            "product_build_consistent": product_build_consistent,
            "configured_runtime_real_write_gate": (
                gate_status.configured_runtime_real_write_gate
            ),
            "runtime_real_write_gate": gate_status.runtime_real_write_gate,
            "live_activation_eligible": (
                self._profile == "BINANCE_LIVE_WRITE"
                and product_build_consistent
                and gate_status.configured_runtime_real_write_gate == "CLOSED"
            ),
            "capital_notice": "计划中的交易金额就是本次边界；激活不再要求独立资金授权，也不会绕过事实、CAP 或 EXE。",
        }

    def activate(
        self,
        payload: ActivationPayload,
        *,
        idempotency_key: str,
        observed_at: datetime,
        order_schedule_snapshot: OrderSchedulePreview | None = None,
    ) -> dict[str, Any]:
        gate_status = self._gate_status()
        if self._profile == "BINANCE_LIVE_READ_ONLY":
            raise ValueError("LIVE_READ_ONLY_ACTIVATION_FORBIDDEN")
        if self._profile == "BINANCE_LIVE_WRITE":
            if gate_status.product_build_consistent is not True:
                raise ValueError("LIVE_WRITE_PRODUCT_BUILD_MISMATCH")
            if gate_status.configured_runtime_real_write_gate != "CLOSED":
                raise ValueError("LIVE_WRITE_GATE_MUST_BE_CLOSED_FOR_ACTIVATION")
        actual_schedule_digest = (
            order_schedule_snapshot.schedule_digest
            if order_schedule_snapshot is not None
            else None
        )
        if payload.expected_schedule_digest != actual_schedule_digest:
            raise ValueError("ACTIVATION_PREVIEW_STALE")
        activation_id = _stable_id(self._environment_id, "activation", idempotency_key)
        with self._connect() as connection:
            planning = PostgreSQLPlanningRepository(connection, self._environment_id)
            try:
                with connection.transaction():
                    activation = PlanningApplicationService(
                        connection, self._environment_id
                    ).activate_version(
                        plan_version_id=payload.plan_version_id,
                        activation_id=activation_id,
                        environment_kind=self._environment_kind,
                        authority_class=self._authority_class,
                        product_build_id=self._product_build_id,
                        observed_at=observed_at,
                        order_schedule_snapshot=order_schedule_snapshot,
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
                if activation.plan_version_ref != payload.plan_version_id:
                    raise ValueError("IDEMPOTENCY_CONTENT_CONFLICT") from None
                persisted_digest = (
                    activation.order_schedule_snapshot.schedule_digest
                    if activation.order_schedule_snapshot is not None
                    else None
                )
                if persisted_digest != actual_schedule_digest:
                    raise ValueError("IDEMPOTENCY_CONTENT_CONFLICT") from None
        return self._activation_response(activation)

    def activation_replay(
        self,
        payload: ActivationPayload,
        *,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        """Replay a committed activation before any rule refresh or readiness check."""

        activation_id = _stable_id(self._environment_id, "activation", idempotency_key)
        with self._connect() as connection, connection.transaction():
            try:
                activation = PostgreSQLPlanningRepository(
                    connection,
                    self._environment_id,
                ).get_activation(activation_id)
            except PlanningConflict as exc:
                if str(exc) == "ACTIVATION_NOT_FOUND":
                    return None
                raise
        persisted_digest = (
            activation.order_schedule_snapshot.schedule_digest
            if activation.order_schedule_snapshot is not None
            else None
        )
        if (
            activation.plan_version_ref != payload.plan_version_id
            or persisted_digest != payload.expected_schedule_digest
        ):
            raise ValueError("IDEMPOTENCY_CONTENT_CONFLICT")
        return self._activation_response(activation)

    def _activation_response(self, activation: Any) -> dict[str, Any]:
        return {
            "activation": activation.model_dump(mode="json"),
            "venue_write_created": False,
            "runtime_real_write_gate": self._gate_status().runtime_real_write_gate,
        }

    def list_activations(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT a.activation_id,
                       v.terms ->> 'plan_name',
                       v.terms ->> 'created_at',
                       v.terms ->> 'creator_kind'
                FROM halpha.plan_activation a
                LEFT JOIN halpha.trade_plan_version v
                  ON v.environment_id = a.environment_id
                 AND v.plan_version_id = a.plan_version_ref
                WHERE a.environment_id = %s ORDER BY a.created_at DESC
                """,
                (self._environment_id,),
            ).fetchall()
            repository = PostgreSQLPlanningRepository(connection, self._environment_id)
            return [
                {
                    **repository.get_activation(str(row[0])).model_dump(mode="json"),
                    "plan_name": str(row[1]) if row[1] is not None else None,
                    "plan_created_at": (
                        str(row[2]) if row[2] is not None else None
                    ),
                    "plan_creator_kind": (
                        str(row[3]) if row[3] is not None else None
                    ),
                }
                for row in rows
            ]

    def activation_detail(self, activation_id: str) -> dict[str, Any]:
        with self._connect() as connection, connection.transaction():
            activation = PostgreSQLPlanningRepository(
                connection, self._environment_id
            ).get_activation(activation_id)
            version = PostgreSQLPlanningRepository(
                connection, self._environment_id
            ).get_version(activation.plan_version_ref)
            if activation.lifecycle is PlanLifecycle.COMPLETED:
                ActivationControlService(
                    connection,
                    self._environment_id,
                ).finalize_completed_activation(
                    activation_id,
                    observed_at=datetime.now(UTC),
                )
            actions = connection.execute(
                """
                SELECT execution_action_id, action_kind, action_class, action_terms,
                       client_order_id, state, state_version, unknown_reason,
                       not_submitted_reason, protection_digest, closure_evidence_digest,
                       created_at, updated_at, execution_profile_ref, account_ref,
                       authority_class, cancel_target, call_started_at,
                       call_completed_at
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
        stopped_categories = {str(category) for row in stops for category in row[0]}
        if "ALL_EXCHANGE_CHANGES" in stopped_categories:
            stopped_categories.update(
                {
                    "NEW_RISK",
                    "PROTECTION",
                    "RISK_REDUCTION_OR_ORDER_MANAGEMENT",
                }
            )
        return {
            "activation": activation.model_dump(mode="json"),
            "plan": {
                "plan_version_id": version.plan_version_id,
                "plan_id": version.plan_id,
                "plan_name": version.plan_name,
                "created_at": (
                    version.created_at.isoformat()
                    if version.created_at is not None
                    else None
                ),
                "creator_kind": (
                    version.creator_kind.value
                    if version.creator_kind is not None
                    else None
                ),
            },
            "decision_basis": version.decision_basis.model_dump(mode="json"),
            "strategy": (
                {
                    "strategy_ref": version.decision_basis.decision_basis_ref,
                    "parameters": version.decision_basis.normalized_parameters,
                }
                if isinstance(version.decision_basis, FixedStrategyPlanBasis)
                else None
            ),
            "order_schedule": (
                activation.order_schedule_snapshot.model_dump(mode="json")
                if activation.order_schedule_snapshot is not None
                else None
            ),
            "capital": {
                "max_margin": version.requested_limits.max_margin,
                "max_notional": version.requested_limits.max_notional,
                "max_allowed_loss": version.requested_limits.max_allowed_loss,
                **dict(activation.rule_state.get("capital", {})),
            },
            "trade_result": summarize_trade_result(
                direction=activation.direction.value,
                action_kinds={str(row[0]): str(row[1]) for row in actions},
                facts=(
                    {
                        "kind": str(row[1]),
                        "payload": dict(row[7]),
                        "action_ref": str(row[8]) if row[8] is not None else None,
                        "source_time": row[4].isoformat() if row[4] is not None else None,
                    }
                    for row in facts
                ),
            ),
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
                    "not_submitted_reason": (
                        str(row[8]) if row[8] is not None else None
                    ),
                    "protection_digest": str(row[9]) if row[9] is not None else None,
                    "closure_evidence_digest": str(row[10])
                    if row[10] is not None
                    else None,
                    "created_at": row[11].isoformat(),
                    "updated_at": row[12].isoformat(),
                    "execution_profile_ref": str(row[13]),
                    "account_ref": str(row[14]),
                    "authority_class": str(row[15]),
                    "cancel_target": dict(row[16]) if row[16] is not None else None,
                    "call_started_at": (
                        row[17].isoformat() if row[17] is not None else None
                    ),
                    "call_completed_at": (
                        row[18].isoformat() if row[18] is not None else None
                    ),
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

    def control_preview(
        self, activation_id: str, intent: ControlIntent
    ) -> dict[str, Any]:
        current = self.activation_detail(activation_id)
        consequences = {
            ControlIntent.STOP_NEW_RISK: "立即阻止新风险；已有查询、保护、撤单和减险责任继续。",
            ControlIntent.RESUME_ACTIVATION: "仅解除执行者连续性暂停；当前计划、事实和安全停止仍需通过。",
            ControlIntent.EXIT_STRATEGY: "进入 EXITING，停止增险并等待执行与闭合责任。",
            ControlIntent.USER_TAKEOVER: "先持久化责任转移，再停止自动发起交易所变更请求；不会自动撤单或平仓。",
        }
        activation = current["activation"]
        capital = current["capital"]
        preview_basis = {
            "activation_id": activation_id,
            "intent": intent.value,
            "activation_state_version": activation["state_version"],
            "lifecycle": activation["lifecycle"],
            "run_state": activation["run_state"],
            "pause_reason": activation["pause_reason"],
            "protection_state": activation["protection_state"],
            "max_loss_reached": bool(capital.get("max_loss_reached")),
        }
        return {
            **current,
            "intent": intent.value,
            "consequence": consequences[intent],
            "preview_digest": content_digest(preview_basis),
            "previewed_at": datetime.now(UTC).isoformat(),
            "resume_eligible": False
            if intent is ControlIntent.RESUME_ACTIVATION
            else None,
            "resume_denial_reasons": (
                ["AUTHORITATIVE_RECONCILIATION_NOT_AVAILABLE"]
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
            **payload.takeover_scope,
            "activation_id": activation_id,
            "cutoff": observed_at.isoformat(),
        }
        if intent is ControlIntent.USER_TAKEOVER:
            # EXE closure attributes the post-handover boundary to this exact
            # immutable command. User-provided scope must not be able to
            # replace that identity.
            scope["command_ref"] = command_id
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
                # User input is never trusted as reconciliation evidence. Only the
                # unique Executor/EXE path can inject authoritative evidence.
                reconciliation_digest=None,
            )
        return receipt.model_dump(mode="json")

    def receipt(self, receipt_id: str) -> dict[str, Any]:
        query = """
                SELECT r.receipt_id, r.command_id, r.processing_owner, r.state,
                       r.state_version, r.reason_code, r.result,
                       r.pending_responsibility_refs, r.content_digest,
                       r.created_at, r.updated_at, c.target_ref
                FROM halpha.receipt r
                JOIN halpha.command c
                  ON c.environment_id = r.environment_id
                 AND c.command_id = r.command_id
                WHERE r.environment_id = %s AND r.receipt_id = %s
                """
        with self._connect() as connection, connection.transaction():
            row = connection.execute(
                query,
                (self._environment_id, receipt_id),
            ).fetchone()
            if row is not None and str(row[3]) == "PROCESSING":
                ActivationControlService(
                    connection,
                    self._environment_id,
                ).finalize_completed_activation(
                    str(row[11]),
                    observed_at=datetime.now(UTC),
                )
                row = connection.execute(
                    query,
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
