"""CAP's private PostgreSQL writer and allocation lock boundary."""

from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from halpha.capital.models import (
    AccountCapitalLimitVersion,
    AllocationStatus,
    MachineAuthorizationVersion,
    PlanAllocation,
    StopStateVersion,
)


class CapitalConflict(RuntimeError):
    pass


class PostgreSQLCapitalRepository:
    """Only this repository writes the four CAP record families."""

    def __init__(self, connection: Connection[Any], environment_id: str) -> None:
        self._connection = connection
        self._environment_id = environment_id

    def insert_account_limit(self, limit: AccountCapitalLimitVersion) -> None:
        if limit.environment_id != self._environment_id:
            raise CapitalConflict("AUTHORIZATION_MISMATCH")
        self._connection.execute(
            """
            INSERT INTO halpha.account_capital_limit_version (
                capital_limit_version_id, environment_id, environment_kind,
                authority_class, account_ref, quote_asset, version, effective_at,
                max_margin, max_notional, max_allowed_loss, max_action_notional,
                scope, content_digest
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                limit.capital_limit_version_id,
                limit.environment_id,
                limit.environment_kind.value,
                limit.authority_class.value,
                limit.account_ref,
                limit.quote_asset,
                limit.version,
                limit.effective_at,
                limit.max_margin,
                limit.max_notional,
                limit.max_allowed_loss,
                limit.max_action_notional,
                Jsonb(limit.scope),
                limit.content_digest,
            ),
        )

    def get_account_limit(
        self, capital_limit_version_id: str, *, for_update: bool = False
    ) -> AccountCapitalLimitVersion:
        suffix = " FOR UPDATE" if for_update else ""
        row = self._connection.execute(
            """
            SELECT capital_limit_version_id, environment_id, environment_kind,
                   authority_class, account_ref, quote_asset, version, effective_at,
                   max_margin, max_notional, max_allowed_loss, max_action_notional,
                   scope, content_digest
            FROM halpha.account_capital_limit_version
            WHERE environment_id = %s AND capital_limit_version_id = %s
            """ + suffix,
            (self._environment_id, capital_limit_version_id),
        ).fetchone()
        if row is None:
            raise CapitalConflict("CAPITAL_LIMIT_NOT_FOUND")
        return AccountCapitalLimitVersion(
            capital_limit_version_id=str(row[0]),
            environment_id=str(row[1]),
            environment_kind=str(row[2]),
            authority_class=str(row[3]),
            account_ref=str(row[4]),
            quote_asset=str(row[5]),
            version=int(row[6]),
            effective_at=row[7],
            max_margin=str(row[8]),
            max_notional=str(row[9]),
            max_allowed_loss=str(row[10]),
            max_action_notional=str(row[11]),
            scope=dict(row[12]),
            content_digest=str(row[13]),
        )

    def lock_open_allocations(
        self, *, authority_class: str, quote_asset: str
    ) -> tuple[PlanAllocation, ...]:
        rows = self._connection.execute(
            """
            SELECT allocation_id, activation_id, capital_limit_version_ref,
                   environment_id, environment_kind, authority_class, quote_asset,
                   max_margin, max_notional, max_allowed_loss, status, state_version,
                   exposure_summary, max_loss_reached, loss_latch_digest, closure_digest
            FROM halpha.plan_allocation
            WHERE environment_id = %s AND authority_class = %s AND quote_asset = %s
              AND status <> 'RELEASED'
            ORDER BY allocation_id
            FOR UPDATE
            """,
            (self._environment_id, authority_class, quote_asset),
        ).fetchall()
        allocations = []
        for row in rows:
            exposure = dict(row[12])
            allocations.append(
                PlanAllocation(
                    allocation_id=str(row[0]),
                    activation_id=str(row[1]),
                    capital_limit_version_ref=str(row[2]),
                    environment_id=str(row[3]),
                    environment_kind=str(row[4]),
                    authority_class=str(row[5]),
                    quote_asset=str(row[6]),
                    max_margin=str(row[7]),
                    max_notional=str(row[8]),
                    max_allowed_loss=str(row[9]),
                    status=str(row[10]),
                    state_version=int(row[11]),
                    current_margin=str(exposure.get("current_margin", "0")),
                    current_notional=str(exposure.get("current_notional", "0")),
                    activation_loss=str(exposure.get("activation_loss", "0")),
                    max_loss_reached=bool(row[13]),
                    loss_latch_digest=str(row[14]) if row[14] is not None else None,
                    closure_digest=str(row[15]) if row[15] is not None else None,
                )
            )
        return tuple(allocations)

    def lock_account_scope(self, *, account_ref: str, quote_asset: str) -> None:
        """Serialize allocation decisions across every version of one account scope."""

        rows = self._connection.execute(
            """
            SELECT capital_limit_version_id
            FROM halpha.account_capital_limit_version
            WHERE environment_id = %s AND account_ref = %s AND quote_asset = %s
            ORDER BY capital_limit_version_id
            FOR UPDATE
            """,
            (self._environment_id, account_ref, quote_asset),
        ).fetchall()
        if not rows:
            raise CapitalConflict("CAPITAL_LIMIT_NOT_FOUND")

    def insert_authorization(self, authorization: MachineAuthorizationVersion) -> None:
        self._connection.execute(
            """
            INSERT INTO halpha.machine_authorization_version (
                authorization_version_id, environment_id, environment_kind,
                authority_class, activation_id, plan_version_ref, account_ref,
                instrument_ref, direction, version, valid_from, valid_until,
                allowed_actions, terms, content_digest
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                authorization.authorization_version_id,
                authorization.environment_id,
                authorization.environment_kind.value,
                authorization.authority_class.value,
                authorization.activation_id,
                authorization.plan_version_ref,
                authorization.account_ref,
                authorization.instrument_ref,
                authorization.direction,
                authorization.version,
                authorization.valid_from,
                authorization.valid_until,
                sorted(authorization.allowed_actions),
                Jsonb(authorization.terms),
                authorization.content_digest,
            ),
        )

    def get_authorization(
        self,
        authorization_version_id: str,
    ) -> MachineAuthorizationVersion:
        row = self._connection.execute(
            """
            SELECT authorization_version_id, environment_id, environment_kind,
                   authority_class, activation_id, plan_version_ref, account_ref,
                   instrument_ref, direction, version, valid_from, valid_until,
                   allowed_actions, terms, content_digest
            FROM halpha.machine_authorization_version
            WHERE environment_id = %s AND authorization_version_id = %s
            """,
            (self._environment_id, authorization_version_id),
        ).fetchone()
        if row is None:
            raise CapitalConflict("AUTHORIZATION_NOT_FOUND")
        return MachineAuthorizationVersion(
            authorization_version_id=str(row[0]),
            environment_id=str(row[1]),
            environment_kind=str(row[2]),
            authority_class=str(row[3]),
            activation_id=str(row[4]),
            plan_version_ref=str(row[5]),
            account_ref=str(row[6]),
            instrument_ref=str(row[7]),
            direction=str(row[8]),
            version=int(row[9]),
            valid_from=row[10],
            valid_until=row[11],
            allowed_actions=frozenset(row[12]),
            terms=dict(row[13]),
            content_digest=str(row[14]),
        )

    def get_authorization_for_activation(
        self,
        activation_id: str,
    ) -> MachineAuthorizationVersion:
        row = self._connection.execute(
            """
            SELECT authorization_version_id, environment_id, environment_kind,
                   authority_class, activation_id, plan_version_ref, account_ref,
                   instrument_ref, direction, version, valid_from, valid_until,
                   allowed_actions, terms, content_digest
            FROM halpha.machine_authorization_version
            WHERE environment_id = %s AND activation_id = %s
            """,
            (self._environment_id, activation_id),
        ).fetchone()
        if row is None:
            raise CapitalConflict("AUTHORIZATION_NOT_FOUND")
        return MachineAuthorizationVersion(
            authorization_version_id=str(row[0]),
            environment_id=str(row[1]),
            environment_kind=str(row[2]),
            authority_class=str(row[3]),
            activation_id=str(row[4]),
            plan_version_ref=str(row[5]),
            account_ref=str(row[6]),
            instrument_ref=str(row[7]),
            direction=str(row[8]),
            version=int(row[9]),
            valid_from=row[10],
            valid_until=row[11],
            allowed_actions=frozenset(row[12]),
            terms=dict(row[13]),
            content_digest=str(row[14]),
        )

    def insert_allocation(self, allocation: PlanAllocation) -> None:
        self._connection.execute(
            """
            INSERT INTO halpha.plan_allocation (
                allocation_id, environment_id, environment_kind, authority_class,
                activation_id, capital_limit_version_ref, quote_asset, max_margin,
                max_notional, max_allowed_loss, status, state_version,
                exposure_summary, reservation_digest, max_loss_reached,
                loss_fact_cutoff, funding_query_cutoff, loss_latch_digest,
                closure_digest, released_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                allocation.allocation_id,
                allocation.environment_id,
                allocation.environment_kind.value,
                allocation.authority_class.value,
                allocation.activation_id,
                allocation.capital_limit_version_ref,
                allocation.quote_asset,
                allocation.max_margin,
                allocation.max_notional,
                allocation.max_allowed_loss,
                allocation.status.value,
                allocation.state_version,
                Jsonb(
                    {
                        "current_margin": allocation.current_margin,
                        "current_notional": allocation.current_notional,
                        "activation_loss": allocation.activation_loss,
                    }
                ),
                "0" * 64,
                allocation.max_loss_reached,
                allocation.loss_fact_cutoff,
                allocation.funding_query_cutoff,
                allocation.loss_latch_digest,
                allocation.closure_digest,
                allocation.released_at,
            ),
        )

    def get_allocation(self, activation_id: str, *, for_update: bool = False) -> PlanAllocation:
        suffix = " FOR UPDATE" if for_update else ""
        row = self._connection.execute(
            """
            SELECT allocation_id, activation_id, capital_limit_version_ref,
                   environment_id, environment_kind, authority_class, quote_asset,
                   max_margin, max_notional, max_allowed_loss, status, state_version,
                   exposure_summary, max_loss_reached, loss_fact_cutoff,
                   funding_query_cutoff, loss_latch_digest, closure_digest,
                   released_at
            FROM halpha.plan_allocation
            WHERE environment_id = %s AND activation_id = %s
            """ + suffix,
            (self._environment_id, activation_id),
        ).fetchone()
        if row is None:
            raise CapitalConflict("ALLOCATION_NOT_FOUND")
        exposure = dict(row[12])
        return PlanAllocation(
            allocation_id=str(row[0]),
            activation_id=str(row[1]),
            capital_limit_version_ref=str(row[2]),
            environment_id=str(row[3]),
            environment_kind=str(row[4]),
            authority_class=str(row[5]),
            quote_asset=str(row[6]),
            max_margin=str(row[7]),
            max_notional=str(row[8]),
            max_allowed_loss=str(row[9]),
            status=str(row[10]),
            state_version=int(row[11]),
            current_margin=str(exposure.get("current_margin", "0")),
            current_notional=str(exposure.get("current_notional", "0")),
            activation_loss=str(exposure.get("activation_loss", "0")),
            max_loss_reached=bool(row[13]),
            loss_fact_cutoff=row[14],
            funding_query_cutoff=row[15],
            loss_latch_digest=str(row[16]) if row[16] is not None else None,
            closure_digest=str(row[17]) if row[17] is not None else None,
            released_at=row[18],
        )

    def update_allocation(self, allocation: PlanAllocation, *, expected_version: int) -> None:
        cursor = self._connection.execute(
            """
            UPDATE halpha.plan_allocation
            SET status = %s, state_version = %s, exposure_summary = %s,
                max_loss_reached = %s, loss_fact_cutoff = %s,
                funding_query_cutoff = %s, loss_latch_digest = %s,
                closure_digest = %s, released_at = %s
            WHERE environment_id = %s AND activation_id = %s AND state_version = %s
            """,
            (
                allocation.status.value,
                allocation.state_version,
                Jsonb(
                    {
                        "current_margin": allocation.current_margin,
                        "current_notional": allocation.current_notional,
                        "activation_loss": allocation.activation_loss,
                    }
                ),
                allocation.max_loss_reached,
                allocation.loss_fact_cutoff,
                allocation.funding_query_cutoff,
                allocation.loss_latch_digest,
                allocation.closure_digest,
                allocation.released_at,
                allocation.environment_id,
                allocation.activation_id,
                expected_version,
            ),
        )
        if cursor.rowcount != 1:
            raise CapitalConflict("VERSION_CONFLICT")

    def lock_current_stop_states(
        self,
        *,
        account_ref: str,
        activation_id: str,
    ) -> tuple[StopStateVersion, ...]:
        rows = self._connection.execute(
            """
            SELECT stop_state_version_id, environment_id, environment_kind,
                   authority_class, account_ref, activation_id, version,
                   stopped_categories, reason, source, started_at,
                   authorization_version_ref, loss_latch_digest,
                   release_rules, content_digest
            FROM halpha.stop_state_version
            WHERE environment_id = %s AND account_ref = %s
              AND (activation_id IS NULL OR activation_id = %s)
            ORDER BY activation_id NULLS FIRST, version DESC
            FOR UPDATE
            """,
            (self._environment_id, account_ref, activation_id),
        ).fetchall()
        latest: dict[str, StopStateVersion] = {}
        for row in rows:
            state = StopStateVersion(
                stop_state_version_id=str(row[0]),
                environment_id=str(row[1]),
                environment_kind=str(row[2]),
                authority_class=str(row[3]),
                account_ref=str(row[4]),
                activation_id=str(row[5]) if row[5] is not None else None,
                version=int(row[6]),
                stopped_categories=frozenset(row[7]),
                reason=str(row[8]),
                source=str(row[9]),
                started_at=row[10],
                authorization_version_ref=(str(row[11]) if row[11] is not None else None),
                loss_latch_digest=str(row[12]) if row[12] is not None else None,
                release_rules=dict(row[13]),
                content_digest=str(row[14]),
            )
            scope_key = state.activation_id or "ACCOUNT"
            latest.setdefault(scope_key, state)
        return tuple(latest[key] for key in sorted(latest))

    def insert_stop_state(self, state: StopStateVersion) -> None:
        self._connection.execute(
            """
            INSERT INTO halpha.stop_state_version (
                stop_state_version_id, environment_id, environment_kind,
                authority_class, account_ref, activation_id, version,
                stopped_categories, reason, source, started_at,
                authorization_version_ref, loss_latch_digest, release_rules,
                content_digest
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                state.stop_state_version_id,
                state.environment_id,
                state.environment_kind.value,
                state.authority_class.value,
                state.account_ref,
                state.activation_id,
                state.version,
                sorted(item.value for item in state.stopped_categories),
                state.reason,
                state.source,
                state.started_at,
                state.authorization_version_ref,
                state.loss_latch_digest,
                Jsonb(state.release_rules),
                state.content_digest,
            ),
        )
