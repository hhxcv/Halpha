"""Validate fail-closed construction gates in the current Halpha L4 plan.

This check deliberately validates only machine-readable current-state consistency.
It does not decide whether an upstream design conflict is semantically resolved and
does not advance any construction or real-write state.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sys
from typing import Any

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN = (
    REPOSITORY_ROOT / "docs/L4/HALPHA-PLAN-001-current-construction-plan.yaml"
)

ALIGNED_STATES = {"ALIGNED", "FULLY_ALIGNED", "ALIGNED_UPSTREAM"}
RESOLVED_CONFLICT_STATES = {
    "ACCEPTED_ALIGNMENT",
    "CLOSED",
    "RESOLVED",
    "SUPERSEDED",
}
NOT_STARTED_PACKAGE_STATES = {"", "BLOCKED", "DEFERRED", "NOT_STARTED", "PLANNED"}
PACKAGE_COMPLETE_STATES = {"COMPLETE", "COMPLETED"}
LIVE_WRITE_BUILD_CAPABILITY_STATES = {"NOT_QUALIFIED", "QUALIFIED"}
B05_CONSTRUCTION_ELIGIBILITY_STATES = {"BLOCKED", "ELIGIBLE", "AUTHORIZED"}
B05_REAL_CAPITAL_ELIGIBILITY_STATES = {"BLOCKED", "AUTHORIZED"}
RUNTIME_REAL_WRITE_GATE_STATES = {"CLOSED", "OPEN"}
CONSTRUCTION_CONTINUATION_GATE_STATES = {"PENDING", "QUALIFIED", "REJECTED"}
LONG_OBSERVATION_STATES = {"PENDING", "IN_PROGRESS", "QUALIFIED", "REJECTED"}
SHA256_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
VERSION_IDENTITY_PATTERN = re.compile(
    r"(?:^|[/:+;,])(?:version:)?[A-Za-z0-9_.-]*@?v\d+\.\d+\.\d+(?:$|[#+;,])"
)
P0_BUILD_ORDER = (
    "D00",
    "B00",
    "B01",
    "B02",
    "B03",
    "B04_CONSTRUCTION_CONTINUATION_GATE",
    "B05_CONSTRUCTION",
)
RELEASE_AND_REAL_CAPITAL_ORDER = (
    "B04_LONG_OBSERVATION",
    "B04_COMPLETE",
    "CURRENT_BUILD_MANIFEST_QUALIFIED",
    "B05_REAL_CAPITAL_AUTHORIZED",
    "RUNTIME_REAL_WRITE_GATE_OPEN",
)
B05_CONSTRUCTION_DEPENDENCY = "B04.CONSTRUCTION_CONTINUATION_GATE=QUALIFIED"
RESEARCH_PACKAGE_IDS = ("R00", "R01", "R02", "R03")
RESEARCH_BUILD_ORDER = RESEARCH_PACKAGE_IDS
RESEARCH_EFFECT_KEYS = (
    "p0_build_order",
    "b01_b05_scope_dependency_status_evidence",
    "live_write_build_capability",
    "b05_construction_eligibility",
    "b05_real_capital_eligibility",
    "runtime_real_write_gate",
    "product_database_or_migration",
    "product_process_or_write_path",
    "product_release_group",
)
RESEARCH_RUNTIME_STATES = {"PAUSED", "RUNNING", "STOPPED"}
RESEARCH_OVERLAP_QUALIFICATION_STATES = {"NOT_QUALIFIED", "QUALIFIED"}
RESEARCH_POLICY_STATES = {"NOT_FROZEN", "FROZEN"}
RESEARCH_EXPLICIT_ELIGIBILITY_STATES = {"NOT_AUTHORIZED", "ELIGIBLE", "AUTHORIZED"}
RESEARCH_PACKAGE_EFFECT_KEYS = (
    "migration",
    "runtime",
    "release",
    "authority",
    "credential",
)
LIVE_WRITE_GATE_STATE_FIELDS = (
    "live_write_build_capability",
    "b05_real_capital_eligibility",
    "runtime_real_write_gate",
)
LIVE_WRITE_GATE_ELIGIBILITY_INPUTS = (
    "final_build_manifest_digest",
    "user_authorization_ref",
    "account_capital_limit_version_ref",
)
LIVE_WRITE_GATE_OPEN_INPUTS = (
    "machine_authorization_version_ref",
    "plan_allocation_ref",
)
LIVE_WRITE_GATE_PHASE_ORDER = (
    "B05_REAL_CAPITAL_ELIGIBILITY_CLOSED",
    "EXISTING_ACTIVATION_RUNTIME_OPEN",
)


@dataclass(frozen=True)
class Violation:
    code: str
    path: str
    message: str


class PlanLoadError(RuntimeError):
    """Raised when the current plan cannot be read as a YAML mapping."""


def _normalize(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().upper().replace("-", "_").replace(" ", "_")


def _mapping(
    value: object,
    path: str,
    violations: list[Violation],
) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    violations.append(Violation("GOV-SCHEMA-001", path, "must be a mapping"))
    return {}


def _is_blocked(value: object) -> bool:
    return _normalize(value).startswith("BLOCKED")


def _is_started_or_later(value: object) -> bool:
    return _normalize(value) not in NOT_STARTED_PACKAGE_STATES


def _is_complete(value: object) -> bool:
    return _normalize(value) in PACKAGE_COMPLETE_STATES


def _string_sequence(value: object) -> list[str] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            return None
        result.append(item.strip())
    return result


def _is_bound_contract_identity(value: object) -> bool:
    if not isinstance(value, str):
        return False
    identity = value.strip()
    return bool(
        SHA256_DIGEST_PATTERN.fullmatch(identity)
        or GIT_COMMIT_PATTERN.fullmatch(identity)
        or VERSION_IDENTITY_PATTERN.search(identity)
    )


def _parse_timestamp(
    value: object,
    path: str,
    violations: list[Violation],
) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            violations.append(
                Violation("GOV-TIME-001", path, "must be an ISO-8601 timestamp")
            )
            return None
    else:
        violations.append(Violation("GOV-TIME-001", path, "must be an ISO-8601 timestamp"))
        return None
    if parsed.tzinfo is None:
        violations.append(Violation("GOV-TIME-001", path, "must include a UTC offset"))
        return None
    return parsed.astimezone(timezone.utc)


def _validate_accepted_design_set_closure(
    plan: Mapping[str, Any],
    violations: list[Violation],
) -> None:
    """Keep the L4 accepted design declaration and normative basis in sync."""

    if "accepted_design_set" not in plan and "basis" not in plan:
        return

    design_set = _mapping(
        plan.get("accepted_design_set"), "accepted_design_set", violations
    )
    basis = _mapping(plan.get("basis"), "basis", violations)
    upper_level = _string_sequence(design_set.get("upper_level"))
    l2_revisions = _string_sequence(design_set.get("l2_revisions"))
    l3_revisions = _string_sequence(design_set.get("l3"))
    accepted_basis = _string_sequence(basis.get("accepted"))
    if (
        upper_level is None
        or l2_revisions is None
        or l3_revisions is None
        or accepted_basis is None
    ):
        violations.append(
            Violation(
                "GOV-DESIGN-SET-001",
                "accepted_design_set / basis.accepted",
                "upper_level, l2_revisions, l3, and basis.accepted must be lists of non-empty revision references",
            )
        )
        return

    declared = upper_level + l2_revisions
    full_design_set = declared + l3_revisions
    if len(set(full_design_set)) != len(full_design_set) or len(
        set(accepted_basis)
    ) != len(accepted_basis):
        violations.append(
            Violation(
                "GOV-DESIGN-SET-001",
                "accepted_design_set / basis.accepted",
                "accepted revision references must not be duplicated",
            )
        )

    declared_set = set(declared)
    basis_set = set(accepted_basis)
    if declared_set != basis_set:
        missing_from_design_set = sorted(basis_set - declared_set)
        missing_from_basis = sorted(declared_set - basis_set)
        violations.append(
            Violation(
                "GOV-DESIGN-SET-002",
                "accepted_design_set / basis.accepted",
                "accepted design closure differs: "
                f"missing_from_design_set={missing_from_design_set}, "
                f"missing_from_basis={missing_from_basis}",
            )
        )


def _validate_research_package_contract(
    package_id: str,
    record: Mapping[str, Any],
    violations: list[Violation],
) -> None:
    """Require the ENG-003 package contract before eligibility or execution."""

    package_path = f"construction_packages.{package_id}"

    if _normalize(record.get("contract_state")) != "FROZEN":
        violations.append(
            Violation(
                "GOV-RESEARCH-CONTRACT-001",
                f"{package_path}.contract_state",
                "must be FROZEN before eligibility or execution",
            )
        )

    if record.get("id") != package_id:
        violations.append(
            Violation(
                "GOV-RESEARCH-CONTRACT-001",
                f"{package_path}.id",
                f"must be {package_id}",
            )
        )

    semantic_scopes = record.get("semantic_scopes")
    if (
        not isinstance(semantic_scopes, Sequence)
        or isinstance(semantic_scopes, (str, bytes))
        or not semantic_scopes
    ):
        violations.append(
            Violation(
                "GOV-RESEARCH-CONTRACT-001",
                f"{package_path}.semantic_scopes",
                "must contain at least one {owner, anchor} scope",
            )
        )
    else:
        for index, scope in enumerate(semantic_scopes):
            if not isinstance(scope, Mapping) or any(
                not isinstance(scope.get(field), str)
                or not str(scope.get(field)).strip()
                for field in ("owner", "anchor")
            ):
                violations.append(
                    Violation(
                        "GOV-RESEARCH-CONTRACT-001",
                        f"{package_path}.semantic_scopes[{index}]",
                        "must bind non-empty owner and anchor values",
                    )
                )

    base_revision = record.get("base_revision")
    if not isinstance(base_revision, str) or not GIT_COMMIT_PATTERN.fullmatch(
        base_revision.strip()
    ):
        violations.append(
            Violation(
                "GOV-RESEARCH-CONTRACT-002",
                f"{package_path}.base_revision",
                "must bind a full lowercase 40-hex Git commit; package-start evidence must separately prove the commit is clean and carries the declared plan identity",
            )
        )

    owned_paths = _string_sequence(record.get("owned_paths"))
    if not owned_paths:
        violations.append(
            Violation(
                "GOV-RESEARCH-CONTRACT-001",
                f"{package_path}.owned_paths",
                "must contain at least one explicit owned path",
            )
        )

    contracts = _mapping(
        record.get("contracts"), f"{package_path}.contracts", violations
    )
    inputs = contracts.get("inputs")
    if (
        not isinstance(inputs, Sequence)
        or isinstance(inputs, (str, bytes))
        or not inputs
    ):
        violations.append(
            Violation(
                "GOV-RESEARCH-CONTRACT-001",
                f"{package_path}.contracts.inputs",
                "must contain version-, commit-, or digest-bound inputs",
            )
        )
    else:
        for index, contract_input in enumerate(inputs):
            if (
                not isinstance(contract_input, Mapping)
                or not isinstance(contract_input.get("ref"), str)
                or not str(contract_input.get("ref")).strip()
                or not _is_bound_contract_identity(contract_input.get("identity"))
            ):
                violations.append(
                    Violation(
                        "GOV-RESEARCH-CONTRACT-001",
                        f"{package_path}.contracts.inputs[{index}]",
                        "must bind a non-empty ref and a semver, full commit, or sha256 identity",
                    )
                )

    outputs = contracts.get("outputs")
    if (
        not isinstance(outputs, Sequence)
        or isinstance(outputs, (str, bytes))
        or not outputs
    ):
        violations.append(
            Violation(
                "GOV-RESEARCH-CONTRACT-001",
                f"{package_path}.contracts.outputs",
                "must contain at least one declared output contract",
            )
        )
    else:
        for index, contract_output in enumerate(outputs):
            if (
                not isinstance(contract_output, Mapping)
                or not isinstance(contract_output.get("ref"), str)
                or not str(contract_output.get("ref")).strip()
            ):
                violations.append(
                    Violation(
                        "GOV-RESEARCH-CONTRACT-001",
                        f"{package_path}.contracts.outputs[{index}]",
                        "must declare a non-empty ref",
                    )
                )

    effects = _mapping(record.get("effects"), f"{package_path}.effects", violations)
    for effect_key in RESEARCH_PACKAGE_EFFECT_KEYS:
        effect_value = effects.get(effect_key)
        if not isinstance(effect_value, str) or not effect_value.strip():
            violations.append(
                Violation(
                    "GOV-RESEARCH-CONTRACT-001",
                    f"{package_path}.effects.{effect_key}",
                    "must explicitly record NONE or the bounded effect",
                )
            )
        if package_id in {"R00", "R01", "R02"} and _normalize(effect_value) != "NONE":
            violations.append(
                Violation(
                    "GOV-RESEARCH-CONTRACT-003",
                    f"{package_path}.effects.{effect_key}",
                    "must be NONE for isolated R00-R02 work",
                )
            )

    integration_gate = record.get("integration_gate")
    if not isinstance(integration_gate, str) or not integration_gate.strip():
        violations.append(
            Violation(
                "GOV-RESEARCH-CONTRACT-001",
                f"{package_path}.integration_gate",
                "must name the package integration gate",
            )
        )

    exit_evidence = _mapping(
        record.get("exit_evidence"), f"{package_path}.exit_evidence", violations
    )
    if not _string_sequence(exit_evidence.get("requirements")):
        violations.append(
            Violation(
                "GOV-RESEARCH-CONTRACT-001",
                f"{package_path}.exit_evidence.requirements",
                "must contain at least one exit-evidence requirement",
            )
        )
    output_revision = exit_evidence.get("output_revision")
    if _is_complete(record.get("status")) and (
        not isinstance(output_revision, str)
        or not GIT_COMMIT_PATTERN.fullmatch(output_revision.strip())
    ):
        violations.append(
            Violation(
                "GOV-RESEARCH-CONTRACT-004",
                f"{package_path}.exit_evidence.output_revision",
                "must bind a full Git output commit when the package is complete; exit evidence must separately prove it is clean",
            )
        )


def _validate_b04_observation_gates(
    b04: Mapping[str, Any],
    *,
    now: datetime,
    violations: list[Violation],
) -> tuple[str, str]:
    gate_path = "construction_packages.B04.construction_continuation_gate"
    gate = _mapping(b04.get("construction_continuation_gate"), gate_path, violations)
    long_path = "construction_packages.B04.long_observation"
    long_observation = _mapping(b04.get("long_observation"), long_path, violations)

    expected_gate_values = {
        "purpose": "SUCCESSOR_CONSTRUCTION_ONLY",
        "target_blocking_hours": 8,
        "hard_max_blocking_hours": 24,
        "decision_semantics": "POINT_IN_TIME_IMPACT_SCOPED_CONSTRUCTION_PERMISSION",
        "evidence_composition": "PLATFORM_CONTINUITY_PLUS_CURRENT_BUILD_IMMEDIATE_QUALIFICATION",
    }
    for field, expected in expected_gate_values.items():
        if gate.get(field) != expected:
            violations.append(
                Violation(
                    "GOV-CONTINUATION-GATE-001",
                    f"{gate_path}.{field}",
                    f"must remain {expected!r}",
                )
            )

    required = _string_sequence(gate.get("required"))
    expected_required = (
        "PLATFORM_CONTINUITY_AT_LEAST_8_WINDOWS_AWAKE_HOURS_QUALIFIED",
        "CURRENT_BUILD_IMMEDIATE_AUTOMATED_INTEGRATION_DEMO_FAULT_AND_ROLLBACK_CHECKS_QUALIFIED",
        "CURRENT_BUILD_STARTUP_SMOKE_QUALIFIED",
        "RUNTIME_REAL_WRITE_GATE_CLOSED_AT_DECISION",
        "NO_UNISOLATED_CORE_DEFECT",
    )
    if tuple(required or ()) != expected_required:
        violations.append(
            Violation(
                "GOV-CONTINUATION-GATE-001",
                f"{gate_path}.required",
                f"must remain {list(expected_required)}",
            )
        )

    permits = _string_sequence(gate.get("permits"))
    if tuple(permits or ()) != ("SEPARATELY_AUTHORIZED_SUCCESSOR_CONSTRUCTION",):
        violations.append(
            Violation(
                "GOV-CONTINUATION-GATE-001",
                f"{gate_path}.permits",
                "must permit only separately authorized successor construction",
            )
        )
    does_not_permit = _string_sequence(gate.get("does_not_permit"))
    expected_denials = (
        "B04_COMPLETE",
        "BUILD_MANIFEST_RELEASE_ELIGIBLE",
        "B05_REAL_CAPITAL_ACTIVATION",
        "RUNTIME_REAL_WRITE_GATE_OPEN",
    )
    if tuple(does_not_permit or ()) != expected_denials:
        violations.append(
            Violation(
                "GOV-CONTINUATION-GATE-001",
                f"{gate_path}.does_not_permit",
                f"must remain {list(expected_denials)}",
            )
        )

    gate_status = _normalize(gate.get("status"))
    if gate_status not in CONSTRUCTION_CONTINUATION_GATE_STATES:
        violations.append(
            Violation(
                "GOV-CONTINUATION-GATE-001",
                f"{gate_path}.status",
                f"must be one of {sorted(CONSTRUCTION_CONTINUATION_GATE_STATES)}",
            )
        )

    started_at = _parse_timestamp(gate.get("started_at"), f"{gate_path}.started_at", violations)
    target_at = _parse_timestamp(
        gate.get("target_decision_at"), f"{gate_path}.target_decision_at", violations
    )
    hard_deadline_at = _parse_timestamp(
        gate.get("hard_deadline_at"), f"{gate_path}.hard_deadline_at", violations
    )
    if started_at and target_at and target_at - started_at != timedelta(hours=8):
        violations.append(
            Violation(
                "GOV-CONTINUATION-TIME-001",
                f"{gate_path}.target_decision_at",
                "must be exactly 8 hours after started_at",
            )
        )
    if started_at and hard_deadline_at and hard_deadline_at - started_at != timedelta(hours=24):
        violations.append(
            Violation(
                "GOV-CONTINUATION-TIME-001",
                f"{gate_path}.hard_deadline_at",
                "must be exactly 24 hours after started_at",
            )
        )

    extension = _mapping(gate.get("extension"), f"{gate_path}.extension", violations)
    extension_status = _normalize(extension.get("status"))
    if extension.get("allowed_only_for") != "EXPLICIT_DIURNAL_CONSUMER_WITH_OWNER_RECORDED_REASON":
        violations.append(
            Violation(
                "GOV-CONTINUATION-TIME-001",
                f"{gate_path}.extension.allowed_only_for",
                "must remain EXPLICIT_DIURNAL_CONSUMER_WITH_OWNER_RECORDED_REASON",
            )
        )
    if extension_status not in {"NOT_USED", "APPROVED"}:
        violations.append(
            Violation(
                "GOV-CONTINUATION-TIME-001",
                f"{gate_path}.extension.status",
                "must be NOT_USED or APPROVED",
            )
        )
    if extension_status == "APPROVED":
        for field in ("reason", "owner_decision_ref"):
            value = extension.get(field)
            if not isinstance(value, str) or not value.strip():
                violations.append(
                    Violation(
                        "GOV-CONTINUATION-TIME-001",
                        f"{gate_path}.extension.{field}",
                        "must be bound for an approved extension",
                    )
                )
    if gate_status == "PENDING" and target_at and now >= target_at and extension_status != "APPROVED":
        violations.append(
            Violation(
                "GOV-CONTINUATION-TIME-002",
                f"{gate_path}.status",
                "cannot remain PENDING after the 8-hour target without an approved diurnal extension",
            )
        )
    if gate_status == "PENDING" and hard_deadline_at and now >= hard_deadline_at:
        violations.append(
            Violation(
                "GOV-CONTINUATION-TIME-003",
                f"{gate_path}.status",
                "must be QUALIFIED or REJECTED at the 24-hour absolute deadline",
            )
        )

    if "frozen_baseline" in gate:
        violations.append(
            Violation(
                "GOV-CONTINUATION-EVIDENCE-002",
                f"{gate_path}.frozen_baseline",
                "must not bind the construction permission to an exact-build long-observation baseline",
            )
        )

    current_evidence = _mapping(
        gate.get("current_evidence"), f"{gate_path}.current_evidence", violations
    )
    evidence_observed_at = _parse_timestamp(
        current_evidence.get("observed_at"),
        f"{gate_path}.current_evidence.observed_at",
        violations,
    )
    evidence_ref = current_evidence.get("evidence_ref")
    if not isinstance(evidence_ref, str) or not evidence_ref.strip():
        violations.append(
            Violation(
                "GOV-CONTINUATION-EVIDENCE-001",
                f"{gate_path}.current_evidence.evidence_ref",
                "must bind the current evidence artifact",
            )
        )
    evidence_digest = current_evidence.get("evidence_digest")
    if not isinstance(evidence_digest, str) or not SHA256_DIGEST_PATTERN.fullmatch(
        evidence_digest.strip()
    ):
        violations.append(
            Violation(
                "GOV-CONTINUATION-EVIDENCE-001",
                f"{gate_path}.current_evidence.evidence_digest",
                "must bind a lowercase sha256:<64 hex> digest",
            )
        )
    platform = _mapping(
        current_evidence.get("platform_continuity"),
        f"{gate_path}.current_evidence.platform_continuity",
        violations,
    )
    current_build = _mapping(
        current_evidence.get("current_build"),
        f"{gate_path}.current_evidence.current_build",
        violations,
    )
    if gate_status == "QUALIFIED":
        qualified_checks = (
            (
                _normalize(platform.get("status")) == "QUALIFIED",
                "platform_continuity.status",
                "must be QUALIFIED",
            ),
            (
                platform.get("claim")
                == "SAME_BOOT_WINDOWS_AWAKE_PLATFORM_CONTINUITY_AT_LEAST_8H",
                "platform_continuity.claim",
                "must remain the platform-only continuity claim",
            ),
            (
                isinstance(platform.get("awake_elapsed_hours"), (int, float))
                and float(platform["awake_elapsed_hours"]) >= 8.0,
                "platform_continuity.awake_elapsed_hours",
                "must be at least 8",
            ),
            (
                _normalize(current_build.get("status")) == "QUALIFIED",
                "current_build.status",
                "must be QUALIFIED",
            ),
            (
                current_build.get("startup_smoke_qualified") is True,
                "current_build.startup_smoke_qualified",
                "must be true",
            ),
            (
                current_build.get("immediate_tests_qualified") is True,
                "current_build.immediate_tests_qualified",
                "must be true",
            ),
            (
                _normalize(current_evidence.get("runtime_real_write_gate")) == "CLOSED",
                "runtime_real_write_gate",
                "must record CLOSED at the decision",
            ),
            (
                _normalize(current_evidence.get("unisolated_core_defect_status")) == "NONE",
                "unisolated_core_defect_status",
                "must be NONE",
            ),
            (
                _normalize(current_evidence.get("current_build_process_continuity_8h"))
                == "NOT_CLAIMED",
                "current_build_process_continuity_8h",
                "must explicitly remain NOT_CLAIMED",
            ),
        )
        for passed, field, message in qualified_checks:
            if not passed:
                violations.append(
                    Violation(
                        "GOV-CONTINUATION-QUALIFICATION-001",
                        f"{gate_path}.current_evidence.{field}",
                        message,
                    )
                )
        for record, prefix, digest_fields in (
            (platform, "platform_continuity", ("raw_evidence_digest",)),
            (
                current_build,
                "current_build",
                ("product_runtime_source_digest", "junit_digest"),
            ),
        ):
            for field in digest_fields:
                value = record.get(field)
                if not isinstance(value, str) or not SHA256_DIGEST_PATTERN.fullmatch(
                    value.strip()
                ):
                    violations.append(
                        Violation(
                            "GOV-CONTINUATION-EVIDENCE-001",
                            f"{gate_path}.current_evidence.{prefix}.{field}",
                            "must bind a lowercase sha256:<64 hex> digest",
                        )
                    )
        for record, prefix, ref_fields in (
            (platform, "platform_continuity", ("raw_evidence_ref",)),
            (current_build, "current_build", ("junit_ref",)),
        ):
            for field in ref_fields:
                value = record.get(field)
                if not isinstance(value, str) or not value.strip():
                    violations.append(
                        Violation(
                            "GOV-CONTINUATION-EVIDENCE-001",
                            f"{gate_path}.current_evidence.{prefix}.{field}",
                            "must bind an evidence reference",
                        )
                    )
        current_commit = current_build.get("commit_sha")
        if not isinstance(current_commit, str) or not GIT_COMMIT_PATTERN.fullmatch(
            current_commit.strip()
        ):
            violations.append(
                Violation(
                    "GOV-CONTINUATION-EVIDENCE-001",
                    f"{gate_path}.current_evidence.current_build.commit_sha",
                    "must bind a full lowercase 40-hex Git commit",
                )
            )
        if target_at and evidence_observed_at and evidence_observed_at < target_at:
            violations.append(
                Violation(
                    "GOV-CONTINUATION-QUALIFICATION-001",
                    f"{gate_path}.current_evidence.observed_at",
                    "cannot predate the 8-hour target",
                )
            )
        if evidence_observed_at and evidence_observed_at > now:
            violations.append(
                Violation(
                    "GOV-CONTINUATION-QUALIFICATION-001",
                    f"{gate_path}.current_evidence.observed_at",
                    "cannot be in the future relative to the validation decision",
                )
            )

    long_status = _normalize(long_observation.get("status"))
    if long_status not in LONG_OBSERVATION_STATES:
        violations.append(
            Violation(
                "GOV-LONG-OBSERVATION-001",
                f"{long_path}.status",
                f"must be one of {sorted(LONG_OBSERVATION_STATES)}",
            )
        )
    current_baseline = _mapping(
        long_observation.get("current_baseline"),
        f"{long_path}.current_baseline",
        violations,
    )
    baseline_status = _normalize(current_baseline.get("identity_status"))
    if long_status == "PENDING":
        if baseline_status != "PENDING_COMMITTED_BASELINE":
            violations.append(
                Violation(
                    "GOV-LONG-OBSERVATION-BASELINE-001",
                    f"{long_path}.current_baseline.identity_status",
                    "must be PENDING_COMMITTED_BASELINE while long observation is pending",
                )
            )
        for field in ("commit_sha", "source_sha256_digest"):
            if current_baseline.get(field) is not None:
                violations.append(
                    Violation(
                        "GOV-LONG-OBSERVATION-BASELINE-001",
                        f"{long_path}.current_baseline.{field}",
                        "must remain null until an exact committed baseline is frozen",
                    )
                )
    elif baseline_status != "FROZEN":
        violations.append(
            Violation(
                "GOV-LONG-OBSERVATION-BASELINE-001",
                f"{long_path}.current_baseline.identity_status",
                "must be FROZEN after the long observation starts",
            )
        )
    else:
        commit_sha = current_baseline.get("commit_sha")
        if not isinstance(commit_sha, str) or not GIT_COMMIT_PATTERN.fullmatch(
            commit_sha.strip()
        ):
            violations.append(
                Violation(
                    "GOV-LONG-OBSERVATION-BASELINE-001",
                    f"{long_path}.current_baseline.commit_sha",
                    "must bind a full lowercase 40-hex Git commit",
                )
            )
        for field in (
            "source_sha256_digest",
            "nonsecret_configuration_digest",
            "observation_tool_digest",
        ):
            value = current_baseline.get(field)
            if not isinstance(value, str) or not SHA256_DIGEST_PATTERN.fullmatch(
                value.strip()
            ):
                violations.append(
                    Violation(
                        "GOV-LONG-OBSERVATION-BASELINE-001",
                        f"{long_path}.current_baseline.{field}",
                        "must bind a lowercase sha256:<64 hex> digest",
                    )
                )
    windows = _mapping(
        long_observation.get("windows_awake_runtime"),
        f"{long_path}.windows_awake_runtime",
        violations,
    )
    live_read_only = _mapping(
        long_observation.get("live_read_only_market"),
        f"{long_path}.live_read_only_market",
        violations,
    )
    expected_long_values = (
        (windows, "required_hours", 72, "windows_awake_runtime"),
        (live_read_only, "minimum_natural_days", 7, "live_read_only_market"),
        (
            live_read_only,
            "maximum_natural_days_if_no_complete_trigger_or_expiry",
            14,
            "live_read_only_market",
        ),
        (long_observation, "construction_effect", "NON_BLOCKING_AFTER_CONSTRUCTION_CONTINUATION_GATE_QUALIFIED", ""),
        (long_observation, "release_effect", "BLOCKING", ""),
        (long_observation, "real_capital_activation_effect", "BLOCKING", ""),
    )
    for record, field, expected, prefix in expected_long_values:
        if record.get(field) != expected:
            child = f"{prefix}." if prefix else ""
            violations.append(
                Violation(
                    "GOV-LONG-OBSERVATION-001",
                    f"{long_path}.{child}{field}",
                    f"must remain {expected!r}",
                )
            )

    windows_status = _normalize(windows.get("status"))
    live_read_only_status = _normalize(live_read_only.get("status"))
    expected_current_baseline_ref = "construction_packages.B04.long_observation.current_baseline"
    if windows.get("baseline_ref") != expected_current_baseline_ref:
        violations.append(
            Violation(
                "GOV-LONG-OBSERVATION-BASELINE-001",
                f"{long_path}.windows_awake_runtime.baseline_ref",
                f"must remain {expected_current_baseline_ref!r}",
            )
        )
    for record, prefix in (
        (windows, "windows_awake_runtime"),
        (live_read_only, "live_read_only_market"),
    ):
        evidence_ref = record.get("evidence_ref")
        if not isinstance(evidence_ref, str) or not evidence_ref.strip():
            violations.append(
                Violation(
                    "GOV-LONG-OBSERVATION-EVIDENCE-001",
                    f"{long_path}.{prefix}.evidence_ref",
                    "must bind the observation evidence artifact",
                )
            )

    windows_baseline_at: datetime | None = None
    windows_checkpoint_at: datetime | None = None
    if windows_status == "QUALIFIED":
        if not (
            isinstance(windows.get("awake_elapsed_hours"), (int, float))
            and float(windows["awake_elapsed_hours"]) >= 72.0
        ):
            violations.append(
                Violation(
                    "GOV-LONG-OBSERVATION-QUALIFICATION-001",
                    f"{long_path}.windows_awake_runtime.awake_elapsed_hours",
                    "must prove at least 72 Windows awake hours before Windows qualification",
                )
            )
        windows_baseline_at = _parse_timestamp(
            windows.get("baseline_at"),
            f"{long_path}.windows_awake_runtime.baseline_at",
            violations,
        )
        windows_checkpoint_at = _parse_timestamp(
            windows.get("latest_checkpoint_at"),
            f"{long_path}.windows_awake_runtime.latest_checkpoint_at",
            violations,
        )
        if (
            windows_baseline_at
            and windows_checkpoint_at
            and windows_checkpoint_at - windows_baseline_at < timedelta(hours=72)
        ):
            violations.append(
                Violation(
                    "GOV-LONG-OBSERVATION-QUALIFICATION-001",
                    f"{long_path}.windows_awake_runtime.latest_checkpoint_at",
                    "must be at least 72 hours after baseline_at",
                )
            )
        windows_digest = windows.get("evidence_digest")
        if not isinstance(windows_digest, str) or not SHA256_DIGEST_PATTERN.fullmatch(
            windows_digest.strip()
        ):
            violations.append(
                Violation(
                    "GOV-LONG-OBSERVATION-EVIDENCE-001",
                    f"{long_path}.windows_awake_runtime.evidence_digest",
                    "must bind a lowercase sha256:<64 hex> digest before Windows qualification",
                )
            )
        if windows_checkpoint_at and windows_checkpoint_at > now:
            violations.append(
                Violation(
                    "GOV-LONG-OBSERVATION-QUALIFICATION-001",
                    f"{long_path}.windows_awake_runtime.latest_checkpoint_at",
                    "cannot be in the future relative to the validation decision",
                )
            )

    live_started_at: datetime | None = None
    if live_read_only_status in {"IN_PROGRESS", "QUALIFIED"}:
        if windows_status != "QUALIFIED":
            violations.append(
                Violation(
                    "GOV-LONG-OBSERVATION-SEQUENCE-001",
                    f"{long_path}.live_read_only_market.status",
                    "cannot start until the Windows 72-hour observation is QUALIFIED",
                )
            )
        live_started_at = _parse_timestamp(
            live_read_only.get("started_at"),
            f"{long_path}.live_read_only_market.started_at",
            violations,
        )
        if windows_checkpoint_at and live_started_at and live_started_at < windows_checkpoint_at:
            violations.append(
                Violation(
                    "GOV-LONG-OBSERVATION-SEQUENCE-001",
                    f"{long_path}.live_read_only_market.started_at",
                    "cannot predate the qualified Windows 72-hour checkpoint",
                )
            )
        if live_started_at and live_started_at > now:
            violations.append(
                Violation(
                    "GOV-LONG-OBSERVATION-SEQUENCE-001",
                    f"{long_path}.live_read_only_market.started_at",
                    "cannot be in the future relative to the validation decision",
                )
            )
        live_digest = live_read_only.get("evidence_digest")
        if not isinstance(live_digest, str) or not SHA256_DIGEST_PATTERN.fullmatch(
            live_digest.strip()
        ):
            violations.append(
                Violation(
                    "GOV-LONG-OBSERVATION-EVIDENCE-001",
                    f"{long_path}.live_read_only_market.evidence_digest",
                    "must bind a lowercase sha256:<64 hex> digest after LIVE_READ_ONLY starts",
                )
            )

    if live_read_only_status == "QUALIFIED":
        if not (
            isinstance(live_read_only.get("observed_natural_days"), (int, float))
            and 7.0 <= float(live_read_only["observed_natural_days"]) <= 14.0
        ):
            violations.append(
                Violation(
                    "GOV-LONG-OBSERVATION-QUALIFICATION-001",
                    f"{long_path}.live_read_only_market.observed_natural_days",
                    "must prove between 7 and 14 natural days before LIVE_READ_ONLY qualification",
                )
            )
        live_qualified_at = _parse_timestamp(
            live_read_only.get("qualified_at"),
            f"{long_path}.live_read_only_market.qualified_at",
            violations,
        )
        if live_started_at and live_qualified_at:
            live_duration = live_qualified_at - live_started_at
            if live_duration < timedelta(days=7) or live_duration > timedelta(days=14):
                violations.append(
                    Violation(
                        "GOV-LONG-OBSERVATION-QUALIFICATION-001",
                        f"{long_path}.live_read_only_market.qualified_at",
                        "must be between 7 and 14 days after started_at",
                    )
                )
        if live_qualified_at and live_qualified_at > now:
            violations.append(
                Violation(
                    "GOV-LONG-OBSERVATION-QUALIFICATION-001",
                    f"{long_path}.live_read_only_market.qualified_at",
                    "cannot be in the future relative to the validation decision",
                )
            )

    if long_status == "QUALIFIED":
        for child_status, field in (
            (windows_status, "windows_awake_runtime.status"),
            (live_read_only_status, "live_read_only_market.status"),
        ):
            if child_status != "QUALIFIED":
                violations.append(
                    Violation(
                        "GOV-LONG-OBSERVATION-QUALIFICATION-001",
                        f"{long_path}.{field}",
                        "must be QUALIFIED before the parent long observation is QUALIFIED",
                    )
                )

    if _is_complete(b04.get("status")):
        if gate_status != "QUALIFIED" or long_status != "QUALIFIED":
            violations.append(
                Violation(
                    "GOV-LONG-OBSERVATION-002",
                    "construction_packages.B04.status",
                    "cannot be complete until the continuation gate and long observation are both QUALIFIED",
                )
            )

    return gate_status, long_status


def _has_unresolved_upstream_conflicts(formalization: Mapping[str, Any]) -> bool:
    record_status = _normalize(formalization.get("status"))
    if record_status.startswith("BLOCKED") or "UNRESOLVED" in record_status:
        return True
    if "RECORDED_UPSTREAM_CONFLICT" in record_status:
        return True

    alignment = _normalize(formalization.get("alignment"))
    if alignment not in ALIGNED_STATES:
        return True

    conflicts = formalization.get("conflicts", [])
    if not isinstance(conflicts, Sequence) or isinstance(conflicts, (str, bytes)):
        return True

    for conflict in conflicts:
        if not isinstance(conflict, Mapping):
            return True
        resolution = _normalize(
            conflict.get("resolution_status", conflict.get("status"))
        )
        if resolution not in RESOLVED_CONFLICT_STATES:
            return True
    return False


def validate_plan(
    plan: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> list[Violation]:
    """Return every construction-governance violation found in *plan*."""

    violations: list[Violation] = []
    validation_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    current_state = _mapping(plan.get("current_state"), "current_state", violations)
    formalization = _mapping(
        plan.get("formalization_record"), "formalization_record", violations
    )
    d00 = _mapping(
        plan.get("design_formalization_gate"),
        "design_formalization_gate",
        violations,
    )
    b00 = _mapping(
        plan.get("dependency_qualification_gate"),
        "dependency_qualification_gate",
        violations,
    )
    packages = _mapping(
        plan.get("construction_packages"), "construction_packages", violations
    )
    readiness = _mapping(
        plan.get("definition_of_ready_to_start_p0"),
        "definition_of_ready_to_start_p0",
        violations,
    )
    live_write_evidence = _mapping(
        current_state.get("live_write_gate_evidence"),
        "current_state.live_write_gate_evidence",
        violations,
    )
    runtime_configuration = _mapping(
        plan.get("runtime_configuration"),
        "runtime_configuration",
        violations,
    )
    live_write_gate_binding = _mapping(
        runtime_configuration.get("live_write_gate_binding"),
        "runtime_configuration.live_write_gate_binding",
        violations,
    )
    _validate_accepted_design_set_closure(plan, violations)

    expected_gate_wiring = {
        "schema_version": 1,
        "state_separation_required": True,
        "default_effective_gate": "CLOSED",
        "location": "DETACHED_OUTSIDE_REPOSITORY_AND_BUILDMANIFEST",
        "nonsecret": True,
        "eligibility_scope": "EXACT_ONE_ACCOUNT_CAPITAL_LIMIT_VERSION",
        "open_gate_scope": "EXACT_ONE_EXISTING_ACTIVATION",
        "closed_binding_activation_refs": "FORBIDDEN",
        "open_binding_activation_refs": "REQUIRED",
        "file_security_profile": "WINDOWS_PROTECTED_EXACT_DACL_V1",
        "credential_resolution_order": "DATABASE_GATE_BEFORE_BINANCE_SECRETS",
    }
    for field, expected in expected_gate_wiring.items():
        if live_write_gate_binding.get(field) != expected:
            violations.append(
                Violation(
                    "GOV-LIVE-GATE-003",
                    f"runtime_configuration.live_write_gate_binding.{field}",
                    f"must remain {expected!r}",
                )
            )
    state_fields = _string_sequence(live_write_gate_binding.get("state_fields"))
    if tuple(state_fields or ()) != LIVE_WRITE_GATE_STATE_FIELDS:
        violations.append(
            Violation(
                "GOV-LIVE-GATE-003",
                "runtime_configuration.live_write_gate_binding.state_fields",
                f"must remain {list(LIVE_WRITE_GATE_STATE_FIELDS)}",
            )
        )
    eligibility_inputs = _string_sequence(
        live_write_gate_binding.get("eligibility_binding_inputs")
    )
    if tuple(eligibility_inputs or ()) != LIVE_WRITE_GATE_ELIGIBILITY_INPUTS:
        violations.append(
            Violation(
                "GOV-LIVE-GATE-003",
                "runtime_configuration.live_write_gate_binding.eligibility_binding_inputs",
                f"must remain {list(LIVE_WRITE_GATE_ELIGIBILITY_INPUTS)}",
            )
        )
    open_inputs = _string_sequence(
        live_write_gate_binding.get("open_gate_binding_inputs")
    )
    if tuple(open_inputs or ()) != LIVE_WRITE_GATE_OPEN_INPUTS:
        violations.append(
            Violation(
                "GOV-LIVE-GATE-003",
                "runtime_configuration.live_write_gate_binding.open_gate_binding_inputs",
                f"must remain {list(LIVE_WRITE_GATE_OPEN_INPUTS)}",
            )
        )
    phase_order = _string_sequence(live_write_gate_binding.get("phase_order"))
    if tuple(phase_order or ()) != LIVE_WRITE_GATE_PHASE_ORDER:
        violations.append(
            Violation(
                "GOV-LIVE-GATE-003",
                "runtime_configuration.live_write_gate_binding.phase_order",
                f"must remain {list(LIVE_WRITE_GATE_PHASE_ORDER)}",
            )
        )

    package_records: dict[str, Mapping[str, Any]] = {}
    for package_id in ("B01", "B02", "B03", "B04", "B05"):
        package_records[package_id] = _mapping(
            packages.get(package_id),
            f"construction_packages.{package_id}",
            violations,
        )
    continuation_gate_status, long_observation_status = _validate_b04_observation_gates(
        package_records["B04"], now=validation_time, violations=violations
    )
    package_b05_construction = _mapping(
        package_records["B05"].get("construction_eligibility"),
        "construction_packages.B05.construction_eligibility",
        violations,
    )
    package_b05_real_capital = _mapping(
        package_records["B05"].get("real_capital_eligibility"),
        "construction_packages.B05.real_capital_eligibility",
        violations,
    )

    research_enabled = (
        "research_track" in plan
        or "research_build_order" in plan
        or any(package_id in packages for package_id in RESEARCH_PACKAGE_IDS)
    )
    if research_enabled:
        research_track = _mapping(
            plan.get("research_track"), "research_track", violations
        )
        research_packages = {
            package_id: _mapping(
                packages.get(package_id),
                f"construction_packages.{package_id}",
                violations,
            )
            for package_id in RESEARCH_PACKAGE_IDS
        }
    else:
        research_track = {}
        research_packages = {}

    unresolved = _has_unresolved_upstream_conflicts(formalization)
    if unresolved:
        blocked_fields = (
            (
                "formalization_record.status",
                formalization.get("status"),
            ),
            (
                "current_state.design_status",
                current_state.get("design_status"),
            ),
            (
                "design_formalization_gate.status",
                d00.get("status"),
            ),
            (
                "definition_of_ready_to_start_p0.design_status",
                readiness.get("design_status"),
            ),
        )
        for path, value in blocked_fields:
            if not _is_blocked(value):
                violations.append(
                    Violation(
                        "GOV-CONFLICT-001",
                        path,
                        "must be BLOCKED while upstream conflicts remain unresolved",
                    )
                )

        for package_id in ("B01", "B02", "B03", "B04"):
            record = package_records[package_id]
            if not _is_blocked(record.get("eligibility")):
                violations.append(
                    Violation(
                        "GOV-CONFLICT-002",
                        f"construction_packages.{package_id}.eligibility",
                        "must be BLOCKED while upstream conflicts remain unresolved; "
                        "only isolated B00 qualification may continue",
                    )
                )
        for field, record in (
            ("construction_eligibility", package_b05_construction),
            ("real_capital_eligibility", package_b05_real_capital),
        ):
            if _normalize(record.get("status")) != "BLOCKED":
                violations.append(
                    Violation(
                        "GOV-CONFLICT-002",
                        f"construction_packages.B05.{field}.status",
                        "must be BLOCKED while upstream conflicts remain unresolved",
                    )
                )

        if _normalize(current_state.get("runtime_real_write_gate")) != "CLOSED":
            violations.append(
                Violation(
                    "GOV-CONFLICT-003",
                    "current_state.runtime_real_write_gate",
                    "must be CLOSED while upstream conflicts remain unresolved",
                )
            )

    b01_dependencies = package_records["B01"].get("depends_on")
    if not isinstance(b01_dependencies, Sequence) or isinstance(
        b01_dependencies, (str, bytes)
    ):
        violations.append(
            Violation(
                "GOV-DEPENDENCY-001",
                "construction_packages.B01.depends_on",
                "must be a list containing D00=ALIGNED and B00=QUALIFIED",
            )
        )
        normalized_dependencies: set[str] = set()
    else:
        normalized_dependencies = {_normalize(item) for item in b01_dependencies}

    for required_dependency in ("D00=ALIGNED", "B00=QUALIFIED"):
        if required_dependency not in normalized_dependencies:
            violations.append(
                Violation(
                    "GOV-DEPENDENCY-002",
                    "construction_packages.B01.depends_on",
                    f"missing required dependency {required_dependency}",
                )
            )

    expected_package_dependencies = {
        "B02": "B01",
        "B03": "B02",
        "B04": "B03",
    }
    for package_id, expected_dependency in expected_package_dependencies.items():
        dependencies = package_records[package_id].get("depends_on")
        if not isinstance(dependencies, Sequence) or isinstance(
            dependencies, (str, bytes)
        ):
            normalized_package_dependencies: set[str] = set()
        else:
            normalized_package_dependencies = {
                _normalize(item) for item in dependencies
            }
        if expected_dependency not in normalized_package_dependencies:
            violations.append(
                Violation(
                    "GOV-DEPENDENCY-003",
                    f"construction_packages.{package_id}.depends_on",
                    f"missing required dependency {expected_dependency}",
                )
            )

    b05_dependencies = package_records["B05"].get("depends_on")
    normalized_b05_dependencies = _string_sequence(b05_dependencies)
    if tuple(normalized_b05_dependencies or ()) != (B05_CONSTRUCTION_DEPENDENCY,):
        violations.append(
            Violation(
                "GOV-DEPENDENCY-004",
                "construction_packages.B05.depends_on",
                f"must be [{B05_CONSTRUCTION_DEPENDENCY!r}]",
            )
        )

    b00_status = _normalize(b00.get("status"))
    d00_aligned = _normalize(d00.get("status")) in ALIGNED_STATES
    if not d00_aligned:
        for package_id, record in package_records.items():
            if _is_started_or_later(record.get("status")):
                violations.append(
                    Violation(
                        "GOV-SEQUENCE-002",
                        f"construction_packages.{package_id}.status",
                        "cannot advance until D00 is ALIGNED",
                    )
                )

    if b00_status != "QUALIFIED":
        for package_id, record in package_records.items():
            if _is_started_or_later(record.get("status")):
                violations.append(
                    Violation(
                        "GOV-SEQUENCE-001",
                        f"construction_packages.{package_id}.status",
                        f"cannot advance while B00 is {b00_status or 'UNKNOWN'}",
                    )
                )

    for package_id in ("B01", "B02", "B03", "B04"):
        record = package_records[package_id]
        if _is_started_or_later(record.get("status")):
            eligibility = _normalize(record.get("eligibility"))
            if not eligibility or _is_blocked(eligibility):
                violations.append(
                    Violation(
                        "GOV-SEQUENCE-003",
                        f"construction_packages.{package_id}",
                        "cannot advance without explicit non-BLOCKED eligibility",
                    )
                )

    for package_id, expected_dependency in expected_package_dependencies.items():
        if _is_started_or_later(
            package_records[package_id].get("status")
        ) and not _is_complete(package_records[expected_dependency].get("status")):
            violations.append(
                Violation(
                    "GOV-SEQUENCE-004",
                    f"construction_packages.{package_id}.status",
                    f"cannot advance until {expected_dependency} is complete",
                )
            )

    b00_to_b04_complete = (
        not unresolved
        and d00_aligned
        and b00_status == "QUALIFIED"
        and continuation_gate_status == "QUALIFIED"
        and long_observation_status == "QUALIFIED"
        and all(
            _is_complete(package_records[package_id].get("status"))
            for package_id in ("B01", "B02", "B03", "B04")
        )
    )
    build_capability = _normalize(current_state.get("live_write_build_capability"))
    b05_construction_eligibility = _normalize(
        current_state.get("b05_construction_eligibility")
    )
    b05_real_capital_eligibility = _normalize(
        current_state.get("b05_real_capital_eligibility")
    )
    package_b05_construction_status = _normalize(
        package_b05_construction.get("status")
    )
    package_b05_real_capital_status = _normalize(
        package_b05_real_capital.get("status")
    )
    runtime_gate = _normalize(current_state.get("runtime_real_write_gate"))

    deprecated_fields = (
        (current_state, "real_write_status", "current_state.real_write_status"),
        (
            current_state,
            "b05_package_eligibility",
            "current_state.b05_package_eligibility",
        ),
        (
            package_records["B05"],
            "eligibility",
            "construction_packages.B05.eligibility",
        ),
        (
            package_b05_real_capital,
            "capital_scope_ref",
            "construction_packages.B05.real_capital_eligibility.capital_scope_ref",
        ),
    )
    for record, field, path in deprecated_fields:
        if field in record:
            violations.append(
                Violation(
                    "GOV-LIVE-GATE-002",
                    path,
                    "is deprecated; use separate build capability, B05 construction eligibility, B05 real-capital eligibility, and runtime gate fields",
                )
            )

    enum_fields = (
        (
            "current_state.live_write_build_capability",
            build_capability,
            LIVE_WRITE_BUILD_CAPABILITY_STATES,
        ),
        (
            "current_state.b05_construction_eligibility",
            b05_construction_eligibility,
            B05_CONSTRUCTION_ELIGIBILITY_STATES,
        ),
        (
            "construction_packages.B05.construction_eligibility.status",
            package_b05_construction_status,
            B05_CONSTRUCTION_ELIGIBILITY_STATES,
        ),
        (
            "current_state.b05_real_capital_eligibility",
            b05_real_capital_eligibility,
            B05_REAL_CAPITAL_ELIGIBILITY_STATES,
        ),
        (
            "construction_packages.B05.real_capital_eligibility.status",
            package_b05_real_capital_status,
            B05_REAL_CAPITAL_ELIGIBILITY_STATES,
        ),
        (
            "current_state.runtime_real_write_gate",
            runtime_gate,
            RUNTIME_REAL_WRITE_GATE_STATES,
        ),
    )
    for path, value, allowed in enum_fields:
        if value not in allowed:
            violations.append(
                Violation(
                    "GOV-LIVE-GATE-001",
                    path,
                    f"must be one of {sorted(allowed)}",
                )
            )

    expected_construction_requires = (
        "B04_CONSTRUCTION_CONTINUATION_GATE_QUALIFIED",
        "SEPARATE_OWNER_CONSTRUCTION_AUTHORIZATION",
    )
    if tuple(_string_sequence(package_b05_construction.get("requires")) or ()) != expected_construction_requires:
        violations.append(
            Violation(
                "GOV-B05-CONSTRUCTION-001",
                "construction_packages.B05.construction_eligibility.requires",
                f"must remain {list(expected_construction_requires)}",
            )
        )
    expected_construction_permits = (
        "CODE",
        "CONFIGURATION",
        "UI",
        "ROLLBACK",
        "NO_REAL_WRITE_TESTS",
    )
    if tuple(_string_sequence(package_b05_construction.get("permits")) or ()) != expected_construction_permits:
        violations.append(
            Violation(
                "GOV-B05-CONSTRUCTION-001",
                "construction_packages.B05.construction_eligibility.permits",
                f"must remain {list(expected_construction_permits)}",
            )
        )
    expected_construction_denials = (
        "B04_COMPLETE",
        "BUILD_MANIFEST_RELEASE_ELIGIBLE",
        "LIVE_WRITE_CREDENTIAL_LOAD",
        "LIVE_EXECUTION_ACTION_CREATE",
        "REAL_CAPITAL_ACTIVATION",
        "RUNTIME_REAL_WRITE_GATE_OPEN",
    )
    if tuple(_string_sequence(package_b05_construction.get("does_not_permit")) or ()) != expected_construction_denials:
        violations.append(
            Violation(
                "GOV-B05-CONSTRUCTION-001",
                "construction_packages.B05.construction_eligibility.does_not_permit",
                f"must remain {list(expected_construction_denials)}",
            )
        )
    expected_real_capital_requires = (
        "B04_LONG_OBSERVATION_QUALIFIED",
        "CURRENT_BUILD_MANIFEST_QUALIFIED",
        "USER_AUTHORIZATION",
        "CAPITAL_SCOPE_BOUND",
    )
    if tuple(_string_sequence(package_b05_real_capital.get("requires")) or ()) != expected_real_capital_requires:
        violations.append(
            Violation(
                "GOV-B05-REAL-CAPITAL-001",
                "construction_packages.B05.real_capital_eligibility.requires",
                f"must remain {list(expected_real_capital_requires)}",
            )
        )

    if b05_construction_eligibility != package_b05_construction_status:
        violations.append(
            Violation(
                "GOV-B05-CONSTRUCTION-002",
                "current_state.b05_construction_eligibility",
                "must match construction_packages.B05.construction_eligibility.status",
            )
        )
    if b05_real_capital_eligibility != package_b05_real_capital_status:
        violations.append(
            Violation(
                "GOV-B05-REAL-CAPITAL-002",
                "current_state.b05_real_capital_eligibility",
                "must match construction_packages.B05.real_capital_eligibility.status",
            )
        )

    b01_to_b03_complete = all(
        _is_complete(package_records[package_id].get("status"))
        for package_id in ("B01", "B02", "B03")
    )
    if b05_construction_eligibility in {"ELIGIBLE", "AUTHORIZED"}:
        construction_prerequisites = (
            (not unresolved and d00_aligned, "formalization_record", "D00 must be fully aligned"),
            (b00_status == "QUALIFIED", "dependency_qualification_gate.status", "B00 must be QUALIFIED"),
            (b01_to_b03_complete, "construction_packages", "B01-B03 must be complete"),
            (
                continuation_gate_status == "QUALIFIED",
                "construction_packages.B04.construction_continuation_gate.status",
                "B04 construction continuation gate must be QUALIFIED",
            ),
        )
        for passed, path, message in construction_prerequisites:
            if not passed:
                violations.append(Violation("GOV-B05-CONSTRUCTION-003", path, message))

    if b05_construction_eligibility == "AUTHORIZED":
        owner_ref = package_b05_construction.get("owner_authorization_ref")
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            violations.append(
                Violation(
                    "GOV-B05-CONSTRUCTION-004",
                    "construction_packages.B05.construction_eligibility.owner_authorization_ref",
                    "must bind separate owner construction authorization",
                )
            )

    b05_started = _is_started_or_later(package_records["B05"].get("status"))
    if b05_started and b05_construction_eligibility != "AUTHORIZED":
        violations.append(
            Violation(
                "GOV-B05-CONSTRUCTION-005",
                "construction_packages.B05.status",
                "cannot advance until B05 construction eligibility is AUTHORIZED",
            )
        )

    if build_capability == "QUALIFIED" and not b00_to_b04_complete:
        violations.append(
            Violation(
                "GOV-REAL-WRITE-001",
                "current_state.live_write_build_capability",
                "cannot be QUALIFIED until D00/B00, B01-B04, the continuation gate, and long observation are complete",
            )
        )

    if b05_real_capital_eligibility == "AUTHORIZED":
        if not b00_to_b04_complete:
            violations.append(
                Violation(
                    "GOV-REAL-WRITE-002",
                    "current_state.b05_real_capital_eligibility",
                    "cannot be AUTHORIZED until B04 long observation and B04 completion are QUALIFIED",
                )
            )
        if build_capability != "QUALIFIED":
            violations.append(
                Violation(
                    "GOV-REAL-WRITE-002",
                    "current_state.live_write_build_capability",
                    "must be QUALIFIED before B05 real-capital eligibility can be AUTHORIZED",
                )
            )
        if b05_construction_eligibility != "AUTHORIZED":
            violations.append(
                Violation(
                    "GOV-B05-REAL-CAPITAL-003",
                    "current_state.b05_construction_eligibility",
                    "must be AUTHORIZED before real-capital eligibility can be AUTHORIZED",
                )
            )
        real_capital_bindings = (
            ("user_authorization_ref", False),
            ("account_capital_limit_version_ref", False),
            ("build_manifest_digest", True),
        )
        for field, digest_required in real_capital_bindings:
            value = package_b05_real_capital.get(field)
            valid = isinstance(value, str) and bool(value.strip())
            if valid and digest_required:
                valid = bool(SHA256_DIGEST_PATTERN.fullmatch(value.strip()))
            if not valid:
                violations.append(
                    Violation(
                        "GOV-B05-REAL-CAPITAL-004",
                        f"construction_packages.B05.real_capital_eligibility.{field}",
                        "must bind the authorized real-capital decision",
                    )
                )
        matching_live_gate_fields = (
            "user_authorization_ref",
            "account_capital_limit_version_ref",
            "build_manifest_digest",
        )
        if any(
            package_b05_real_capital.get(field) != live_write_evidence.get(field)
            for field in matching_live_gate_fields
        ):
            violations.append(
                Violation(
                    "GOV-B05-REAL-CAPITAL-004",
                    "construction_packages.B05.real_capital_eligibility",
                    "must match the bound user authorization, three-axis capital scope, and BuildManifest evidence",
                )
            )

    if runtime_gate == "OPEN":
        prerequisites = (
            (
                not unresolved and d00_aligned,
                "formalization_record",
                "D00 must be fully aligned with no unresolved conflict",
            ),
            (
                b00_status == "QUALIFIED",
                "dependency_qualification_gate.status",
                "B00 must be QUALIFIED",
            ),
            (
                all(
                    _is_complete(package_records[package_id].get("status"))
                    for package_id in ("B01", "B02", "B03", "B04")
                ) and long_observation_status == "QUALIFIED",
                "construction_packages",
                "B01-B04 and the B04 long observation must be complete",
            ),
            (
                build_capability == "QUALIFIED",
                "current_state.live_write_build_capability",
                "live-write build capability must be QUALIFIED",
            ),
            (
                b05_real_capital_eligibility == "AUTHORIZED"
                and package_b05_real_capital_status == "AUTHORIZED",
                "current_state.b05_real_capital_eligibility",
                "B05 real-capital eligibility must be AUTHORIZED in current state and package record",
            ),
            (
                _normalize(package_records["B05"].get("status")) == "IN_PROGRESS",
                "construction_packages.B05.status",
                "B05 must be IN_PROGRESS while the runtime real-write gate is OPEN",
            ),
        )
        for passed, path, message in prerequisites:
            if not passed:
                violations.append(Violation("GOV-REAL-WRITE-004", path, message))

    if b05_real_capital_eligibility == "AUTHORIZED":
        eligibility_evidence = (
            "observed_at",
            "build_manifest_digest",
            "user_authorization_ref",
            "account_capital_limit_version_ref",
        )
        for field in eligibility_evidence:
            value = live_write_evidence.get(field)
            if not isinstance(value, str) or not value.strip():
                violations.append(
                    Violation(
                        "GOV-REAL-WRITE-005",
                        f"current_state.live_write_gate_evidence.{field}",
                        "must bind B05 real-capital eligibility before a REAL activation can be created",
                    )
                )

    if runtime_gate == "OPEN":
        activation_evidence = (
            "machine_authorization_version_ref",
            "plan_allocation_ref",
            "authorized_activation_id",
        )
        for field in activation_evidence:
            value = live_write_evidence.get(field)
            if not isinstance(value, str) or not value.strip():
                violations.append(
                    Violation(
                        "GOV-REAL-WRITE-005",
                        f"current_state.live_write_gate_evidence.{field}",
                        "must bind the one existing activation before the runtime real-write gate can be OPEN",
                    )
                )

    if b05_real_capital_eligibility == "AUTHORIZED" or runtime_gate == "OPEN":
        live_write_observed_at = _parse_timestamp(
            live_write_evidence.get("observed_at"),
            "current_state.live_write_gate_evidence.observed_at",
            violations,
        )
        if live_write_observed_at and live_write_observed_at > validation_time:
            violations.append(
                Violation(
                    "GOV-REAL-WRITE-EVIDENCE-001",
                    "current_state.live_write_gate_evidence.observed_at",
                    "cannot be in the future relative to the validation decision",
                )
            )

    manifest_digest = live_write_evidence.get("build_manifest_digest")
    if isinstance(manifest_digest, str) and manifest_digest.strip():
        if not SHA256_DIGEST_PATTERN.fullmatch(manifest_digest.strip()):
            violations.append(
                Violation(
                    "GOV-REAL-WRITE-006",
                    "current_state.live_write_gate_evidence.build_manifest_digest",
                    "must be a lowercase sha256:<64 hex> digest",
                )
            )

    build_order = plan.get("build_order")
    if not isinstance(build_order, Sequence) or isinstance(build_order, (str, bytes)):
        violations.append(
            Violation(
                "GOV-BUILD-ORDER-001",
                "build_order",
                f"must remain {list(P0_BUILD_ORDER)}",
            )
        )
    elif tuple(_normalize(item) for item in build_order) != P0_BUILD_ORDER:
        violations.append(
            Violation(
                "GOV-BUILD-ORDER-001",
                "build_order",
                f"must remain {list(P0_BUILD_ORDER)}",
            )
        )

    release_order = plan.get("release_and_real_capital_order")
    if not isinstance(release_order, Sequence) or isinstance(
        release_order, (str, bytes)
    ):
        violations.append(
            Violation(
                "GOV-BUILD-ORDER-002",
                "release_and_real_capital_order",
                f"must remain {list(RELEASE_AND_REAL_CAPITAL_ORDER)}",
            )
        )
    elif (
        tuple(_normalize(item) for item in release_order)
        != RELEASE_AND_REAL_CAPITAL_ORDER
    ):
        violations.append(
            Violation(
                "GOV-BUILD-ORDER-002",
                "release_and_real_capital_order",
                f"must remain {list(RELEASE_AND_REAL_CAPITAL_ORDER)}",
            )
        )

    if research_enabled:
        research_order = plan.get("research_build_order")
        if not isinstance(research_order, Sequence) or isinstance(
            research_order, (str, bytes)
        ):
            normalized_research_order: tuple[str, ...] = ()
        else:
            normalized_research_order = tuple(
                _normalize(item) for item in research_order
            )
        if normalized_research_order != RESEARCH_BUILD_ORDER:
            violations.append(
                Violation(
                    "GOV-RESEARCH-DAG-001",
                    "research_build_order",
                    f"must be {list(RESEARCH_BUILD_ORDER)}",
                )
            )

        required_research_dependencies = {
            "R00": set(),
            "R01": {"R00"},
            "R02": {"R01"},
            "R03": {"R02", "B05", "V01"},
        }
        research_positions = {
            package_id: position
            for position, package_id in enumerate(normalized_research_order)
        }
        for package_id, required in required_research_dependencies.items():
            dependencies = research_packages[package_id].get("depends_on")
            if not isinstance(dependencies, Sequence) or isinstance(
                dependencies, (str, bytes)
            ):
                normalized_dependencies = set()
            else:
                normalized_dependencies = {_normalize(item) for item in dependencies}
            if not required.issubset(normalized_dependencies):
                violations.append(
                    Violation(
                        "GOV-RESEARCH-DAG-001",
                        f"construction_packages.{package_id}.depends_on",
                        f"missing required dependencies {sorted(required - normalized_dependencies)}",
                    )
                )
            for dependency in normalized_dependencies.intersection(
                RESEARCH_PACKAGE_IDS
            ):
                if research_positions.get(
                    dependency, len(RESEARCH_PACKAGE_IDS)
                ) >= research_positions.get(package_id, -1):
                    violations.append(
                        Violation(
                            "GOV-RESEARCH-DAG-002",
                            f"construction_packages.{package_id}.depends_on",
                            f"research dependency {dependency} must precede {package_id}",
                        )
                    )

        owner_authorization = _mapping(
            research_track.get("owner_authorization"),
            "research_track.owner_authorization",
            violations,
        )
        owner_authorization_status = _normalize(owner_authorization.get("status"))
        if owner_authorization_status != "AUTHORIZED":
            violations.append(
                Violation(
                    "GOV-RESEARCH-AUTH-001",
                    "research_track.owner_authorization.status",
                    "must be AUTHORIZED for the explicitly scoped R00-R02 research track",
                )
            )
        owner_decision_ref = owner_authorization.get("decision_ref")
        if not isinstance(owner_decision_ref, str) or not owner_decision_ref.strip():
            violations.append(
                Violation(
                    "GOV-RESEARCH-AUTH-001",
                    "research_track.owner_authorization.decision_ref",
                    "must be a non-empty owner decision reference",
                )
            )

        effects = _mapping(
            research_track.get("r00_r02_effects"),
            "research_track.r00_r02_effects",
            violations,
        )
        for effect_key in RESEARCH_EFFECT_KEYS:
            if _normalize(effects.get(effect_key)) != "NONE":
                violations.append(
                    Violation(
                        "GOV-RESEARCH-EFFECT-001",
                        f"research_track.r00_r02_effects.{effect_key}",
                        "must be NONE",
                    )
                )

        policy = _mapping(
            research_track.get("research_policy"),
            "research_track.research_policy",
            violations,
        )
        policy_status = _normalize(policy.get("status"))
        if policy_status not in RESEARCH_POLICY_STATES:
            violations.append(
                Violation(
                    "GOV-RESEARCH-POLICY-001",
                    "research_track.research_policy.status",
                    f"must be one of {sorted(RESEARCH_POLICY_STATES)}",
                )
            )

        runtime_overlap = _mapping(
            research_track.get("runtime_overlap"),
            "research_track.runtime_overlap",
            violations,
        )
        overlap_qualification = _normalize(runtime_overlap.get("qualification"))
        research_execution_state = _normalize(runtime_overlap.get("execution_state"))
        if overlap_qualification not in RESEARCH_OVERLAP_QUALIFICATION_STATES:
            violations.append(
                Violation(
                    "GOV-RESEARCH-OVERLAP-001",
                    "research_track.runtime_overlap.qualification",
                    f"must be one of {sorted(RESEARCH_OVERLAP_QUALIFICATION_STATES)}",
                )
            )
        if research_execution_state not in RESEARCH_RUNTIME_STATES:
            violations.append(
                Violation(
                    "GOV-RESEARCH-OVERLAP-001",
                    "research_track.runtime_overlap.execution_state",
                    f"must be one of {sorted(RESEARCH_RUNTIME_STATES)}",
                )
            )
        if (
            runtime_gate == "OPEN"
            and overlap_qualification != "QUALIFIED"
            and research_execution_state not in {"PAUSED", "STOPPED"}
        ):
            violations.append(
                Violation(
                    "GOV-RESEARCH-OVERLAP-002",
                    "research_track.runtime_overlap.execution_state",
                    "must be PAUSED or STOPPED while the real-write gate is OPEN and overlap is not qualified",
                )
            )

        for package_id in RESEARCH_PACKAGE_IDS:
            record = research_packages[package_id]
            eligibility = _normalize(record.get("eligibility"))
            package_started = _is_started_or_later(record.get("status"))
            eligibility_is_known = _is_blocked(eligibility) or (
                eligibility in RESEARCH_EXPLICIT_ELIGIBILITY_STATES
            )
            if not eligibility_is_known:
                violations.append(
                    Violation(
                        "GOV-RESEARCH-ELIGIBILITY-001",
                        f"construction_packages.{package_id}.eligibility",
                        "must be an explicit BLOCKED state, NOT_AUTHORIZED, ELIGIBLE, or AUTHORIZED",
                    )
                )
            contract_gate_open = (
                bool(eligibility)
                and not _is_blocked(eligibility)
                and eligibility != "NOT_AUTHORIZED"
            )
            if package_started or contract_gate_open:
                _validate_research_package_contract(package_id, record, violations)
            if package_started:
                if eligibility not in {"ELIGIBLE", "AUTHORIZED"}:
                    violations.append(
                        Violation(
                            "GOV-RESEARCH-SEQUENCE-001",
                            f"construction_packages.{package_id}.eligibility",
                            "must be ELIGIBLE or AUTHORIZED before the package starts",
                        )
                    )

        r00_eligibility = _normalize(research_packages["R00"].get("eligibility"))
        r00_started = _is_started_or_later(research_packages["R00"].get("status"))
        if r00_started or r00_eligibility in {"ELIGIBLE", "AUTHORIZED"}:
            if owner_authorization_status != "AUTHORIZED":
                violations.append(
                    Violation(
                        "GOV-RESEARCH-AUTH-001",
                        "construction_packages.R00.status",
                        "cannot advance without the scoped owner authorization",
                    )
                )

        for package_id, dependency in (("R01", "R00"), ("R02", "R01")):
            package_eligibility = _normalize(
                research_packages[package_id].get("eligibility")
            )
            package_started = _is_started_or_later(
                research_packages[package_id].get("status")
            )
            if (
                package_started or package_eligibility in {"ELIGIBLE", "AUTHORIZED"}
            ) and not _is_complete(research_packages[dependency].get("status")):
                violations.append(
                    Violation(
                        "GOV-RESEARCH-SEQUENCE-002",
                        f"construction_packages.{package_id}.eligibility",
                        f"cannot become eligible or advance until {dependency} is complete",
                    )
                )

        r01_complete = _is_complete(research_packages["R01"].get("status"))
        if r01_complete:
            preexisting_data_boundary = _mapping(
                research_track.get("preexisting_data_boundary"),
                "research_track.preexisting_data_boundary",
                violations,
            )
            confirmation_boundary = preexisting_data_boundary.get(
                "confirmation_eligible_not_before"
            )
            r01_completion_prerequisites = (
                (
                    _is_complete(package_records["B04"].get("status")),
                    "construction_packages.B04.status",
                    "must be complete before R01 can complete",
                ),
                (
                    isinstance(confirmation_boundary, str)
                    and bool(confirmation_boundary.strip()),
                    "research_track.preexisting_data_boundary.confirmation_eligible_not_before",
                    "must bind the post-B04 UTC boundary before R01 can complete",
                ),
                (
                    policy_status == "FROZEN",
                    "research_track.research_policy.status",
                    "must be FROZEN before R01 can complete",
                ),
            )
            for passed, path, message in r01_completion_prerequisites:
                if not passed:
                    violations.append(Violation("GOV-RESEARCH-R01-001", path, message))

        r02_eligibility = _normalize(research_packages["R02"].get("eligibility"))
        r02_started = _is_started_or_later(research_packages["R02"].get("status"))
        if (
            r02_started or r02_eligibility in {"ELIGIBLE", "AUTHORIZED"}
        ) and policy_status != "FROZEN":
            violations.append(
                Violation(
                    "GOV-RESEARCH-POLICY-002",
                    "research_track.research_policy.status",
                    "must be FROZEN before R02 becomes eligible or starts",
                )
            )

        r03_eligibility = _normalize(research_packages["R03"].get("eligibility"))
        r03_started = _is_started_or_later(research_packages["R03"].get("status"))
        if r03_started or r03_eligibility == "AUTHORIZED":
            value_decision = _mapping(
                plan.get("value_decision_gate"),
                "value_decision_gate",
                violations,
            )
            owner_selected_evidence_ref = research_track.get(
                "owner_selected_evidence_ref"
            )
            r03_prerequisites = (
                (
                    _is_complete(research_packages["R02"].get("status")),
                    "construction_packages.R02.status",
                    "R02 must be complete",
                ),
                (
                    _is_complete(package_records["B05"].get("status")),
                    "construction_packages.B05.status",
                    "B05 must be complete",
                ),
                (
                    _is_complete(value_decision.get("status")),
                    "value_decision_gate.status",
                    "V01 must be complete",
                ),
                (
                    isinstance(owner_selected_evidence_ref, str)
                    and bool(owner_selected_evidence_ref.strip()),
                    "research_track.owner_selected_evidence_ref",
                    "owner-selected evidence reference must be bound",
                ),
                (
                    r03_eligibility == "AUTHORIZED",
                    "construction_packages.R03.eligibility",
                    "R03 must be explicitly AUTHORIZED",
                ),
            )
            for passed, path, message in r03_prerequisites:
                if not passed:
                    violations.append(Violation("GOV-RESEARCH-R03-001", path, message))

    return violations


def load_plan(path: Path) -> Mapping[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PlanLoadError(f"cannot read {path}: {exc}") from exc

    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PlanLoadError(f"invalid YAML in {path}: {exc}") from exc

    if not isinstance(loaded, Mapping):
        raise PlanLoadError(f"{path} must contain a YAML mapping")
    return loaded


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "plan",
        nargs="?",
        type=Path,
        default=DEFAULT_PLAN,
        help="current construction plan (defaults to the repository L4 plan)",
    )
    args = parser.parse_args(argv)

    try:
        plan = load_plan(args.plan)
    except PlanLoadError as exc:
        print(f"[ERROR] GOV-LOAD-001 {exc}", file=sys.stderr)
        return 2

    violations = validate_plan(plan)
    for violation in violations:
        print(
            f"[ERROR] {violation.code} {violation.path}: {violation.message}",
            file=sys.stderr,
        )
    if violations:
        print(
            f"Construction governance: {len(violations)} violation(s).", file=sys.stderr
        )
        return 1

    print("Construction governance: 0 violations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
