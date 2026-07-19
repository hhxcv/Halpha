from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import unittest

from governance.validate_construction_plan import validate_plan


def empty_live_write_evidence() -> dict[str, object]:
    return {
        "observed_at": None,
        "build_manifest_digest": None,
        "user_authorization_ref": None,
        "account_capital_limit_version_ref": None,
        "machine_authorization_version_ref": None,
        "plan_allocation_ref": None,
        "authorized_activation_id": None,
    }


def b04_observation_records(
    *,
    continuation_status: str = "PENDING",
    long_status: str = "IN_PROGRESS",
) -> dict[str, object]:
    digest = "sha256:" + "1" * 64
    records = {
        "construction_continuation_gate": {
            "purpose": "SUCCESSOR_CONSTRUCTION_ONLY",
            "target_blocking_hours": 8,
            "hard_max_blocking_hours": 24,
            "status": continuation_status,
            "started_at": "2099-01-01T00:00:00Z",
            "target_decision_at": "2099-01-01T08:00:00Z",
            "hard_deadline_at": "2099-01-02T00:00:00Z",
            "extension": {
                "status": "NOT_USED",
                "allowed_only_for": (
                    "EXPLICIT_DIURNAL_CONSUMER_WITH_OWNER_RECORDED_REASON"
                ),
                "reason": None,
                "owner_decision_ref": None,
            },
            "required": [
                "CURRENT_SOURCE_IMMEDIATE_AUTOMATED_INTEGRATION_DEMO_FAULT_AND_ROLLBACK_CHECKS_QUALIFIED",
                "EXACT_SOURCE_CONFIG_PROCESS_IDENTITY_8_WINDOWS_AWAKE_HOURS",
                "RUNTIME_REAL_WRITE_GATE_CLOSED_AT_DECISION",
                "NO_UNISOLATED_CORE_DEFECT",
            ],
            "permits": ["SEPARATELY_AUTHORIZED_SUCCESSOR_CONSTRUCTION"],
            "does_not_permit": [
                "B04_COMPLETE",
                "BUILD_MANIFEST_RELEASE_ELIGIBLE",
                "B05_REAL_CAPITAL_ACTIVATION",
                "RUNTIME_REAL_WRITE_GATE_OPEN",
            ],
            "frozen_baseline": {
                "identity_status": "FROZEN",
                "commit_sha": "a" * 40,
                "source_sha256_digest": digest,
                "dependency_locks": {"runtime": digest, "frontend": digest},
                "migration_head": "20990101_0001",
                "build_artifacts": {"backend": digest, "frontend": digest},
                "nonsecret_configuration_digest": digest,
                "observation_tool_digest": digest,
                "process_identity_ref": "process://test/b04-observer",
                "dependency_closure": "EXACT_BOUND_CLOSURE",
                "read_only_rule": "BASELINE_AND_OBSERVER_READ_ONLY",
            },
            "current_evidence": {
                "observed_at": "2099-01-01T00:00:00Z",
                "immediate_qualification": "PENDING",
                "windows_awake_identity_hours": 0.0,
                "source_configuration_process_identity_unchanged": True,
                "runtime_real_write_gate": "CLOSED",
                "unisolated_core_defect_status": "UNKNOWN",
                "evidence_ref": "evidence://b04/continuation-gate",
                "evidence_digest": digest,
            },
        },
        "long_observation": {
            "status": long_status,
            "frozen_baseline_ref": (
                "construction_packages.B04.construction_continuation_gate.frozen_baseline"
            ),
            "windows_awake_runtime": {
                "required_hours": 72,
                "status": "IN_PROGRESS",
                "baseline_at": "2026-01-01T00:00:00Z",
                "latest_checkpoint_at": "2026-01-01T01:00:00Z",
                "awake_elapsed_hours": 1.0,
                "evidence_ref": "evidence://b04/windows-72h",
                "evidence_digest": digest,
            },
            "live_read_only_market": {
                "minimum_natural_days": 7,
                "maximum_natural_days_if_no_complete_trigger_or_expiry": 14,
                "status": "PENDING_START_AFTER_WINDOWS_72H",
                "started_at": None,
                "qualified_at": None,
                "observed_natural_days": 0,
                "evidence_ref": "evidence://b04/live-read-only",
                "evidence_digest": None,
            },
            "construction_effect": (
                "NON_BLOCKING_AFTER_CONSTRUCTION_CONTINUATION_GATE_QUALIFIED"
            ),
            "release_effect": "BLOCKING",
            "real_capital_activation_effect": "BLOCKING",
        },
    }
    set_long_observation_status(records["long_observation"], long_status, digest=digest)
    return records


def set_long_observation_status(
    observation: dict[str, object],
    status: str,
    *,
    digest: str = "sha256:" + "1" * 64,
) -> None:
    observation["status"] = status
    windows = observation["windows_awake_runtime"]
    live_read_only = observation["live_read_only_market"]
    if status == "QUALIFIED":
        windows.update(
            {
                "status": "QUALIFIED",
                "baseline_at": "2026-01-01T00:00:00Z",
                "latest_checkpoint_at": "2026-01-04T00:00:00Z",
                "awake_elapsed_hours": 72.0,
                "evidence_digest": digest,
            }
        )
        live_read_only.update(
            {
                "status": "QUALIFIED",
                "started_at": "2026-01-04T00:00:00Z",
                "qualified_at": "2026-01-11T00:00:00Z",
                "observed_natural_days": 7,
                "evidence_digest": digest,
            }
        )
    elif status == "REJECTED":
        windows["status"] = "REJECTED"
        live_read_only["status"] = "REJECTED"


def qualify_b04_observations(
    plan: dict[str, object],
    *,
    long_status: str = "QUALIFIED",
) -> None:
    b04 = plan["construction_packages"]["B04"]
    gate = b04["construction_continuation_gate"]
    gate["status"] = "QUALIFIED"
    gate.update(
        {
            "started_at": "2026-01-01T00:00:00Z",
            "target_decision_at": "2026-01-01T08:00:00Z",
            "hard_deadline_at": "2026-01-02T00:00:00Z",
        }
    )
    gate["current_evidence"]["observed_at"] = "2026-01-01T08:00:00Z"
    gate["current_evidence"].update(
        {
            "immediate_qualification": "QUALIFIED",
            "windows_awake_identity_hours": 8.0,
            "source_configuration_process_identity_unchanged": True,
            "runtime_real_write_gate": "CLOSED",
            "unisolated_core_defect_status": "NONE",
        }
    )
    set_long_observation_status(b04["long_observation"], long_status)


def authorize_b05_construction(plan: dict[str, object]) -> None:
    plan["current_state"]["b05_construction_eligibility"] = "AUTHORIZED"
    construction = plan["construction_packages"]["B05"][
        "construction_eligibility"
    ]
    construction["status"] = "AUTHORIZED"
    construction["owner_authorization_ref"] = "owner://b05-construction/decision-1"


def authorize_b05_real_capital(plan: dict[str, object]) -> None:
    authorize_b05_construction(plan)
    plan["current_state"]["b05_real_capital_eligibility"] = "AUTHORIZED"
    plan["current_state"]["live_write_gate_evidence"] = (
        authorized_live_write_evidence()
    )
    plan["construction_packages"]["B05"]["real_capital_eligibility"][
        "status"
    ] = "AUTHORIZED"
    real_capital = plan["construction_packages"]["B05"][
        "real_capital_eligibility"
    ]
    real_capital.update(
        {
            "user_authorization_ref": "authorization://owner/decision-1",
            "account_capital_limit_version_ref": "cap://account-limit/1",
            "build_manifest_digest": "sha256:" + "a" * 64,
        }
    )


def unresolved_blocked_plan() -> dict[str, object]:
    packages = {
        package_id: {
            "eligibility": "BLOCKED_UNTIL_D00_ALIGNED",
            "depends_on": [previous],
        }
        for package_id, previous in (
            ("B01", "B00=QUALIFIED"),
            ("B02", "B01"),
            ("B03", "B02"),
            ("B04", "B03"),
        )
    }
    packages["B01"]["depends_on"] = ["D00=ALIGNED", "B00=QUALIFIED"]
    packages["B04"].update(b04_observation_records())
    packages["B05"] = {
        "depends_on": ["B04.CONSTRUCTION_CONTINUATION_GATE=QUALIFIED"],
        "construction_eligibility": {
            "status": "BLOCKED",
            "requires": [
                "B04_CONSTRUCTION_CONTINUATION_GATE_QUALIFIED",
                "SEPARATE_OWNER_CONSTRUCTION_AUTHORIZATION",
            ],
            "owner_authorization_ref": None,
            "permits": ["CODE", "CONFIGURATION", "UI", "ROLLBACK", "NO_REAL_WRITE_TESTS"],
            "does_not_permit": [
                "B04_COMPLETE",
                "BUILD_MANIFEST_RELEASE_ELIGIBLE",
                "LIVE_WRITE_CREDENTIAL_LOAD",
                "LIVE_EXECUTION_ACTION_CREATE",
                "REAL_CAPITAL_ACTIVATION",
                "RUNTIME_REAL_WRITE_GATE_OPEN",
            ],
        },
        "real_capital_eligibility": {
            "status": "BLOCKED",
            "requires": [
                "B04_LONG_OBSERVATION_QUALIFIED",
                "CURRENT_BUILD_MANIFEST_QUALIFIED",
                "USER_AUTHORIZATION",
                "CAPITAL_SCOPE_BOUND",
            ],
            "user_authorization_ref": None,
            "account_capital_limit_version_ref": None,
            "build_manifest_digest": None,
        },
    }
    return {
        "build_order": [
            "D00",
            "B00",
            "B01",
            "B02",
            "B03",
            "B04_CONSTRUCTION_CONTINUATION_GATE",
            "B05_CONSTRUCTION",
        ],
        "release_and_real_capital_order": [
            "B04_LONG_OBSERVATION",
            "B04_COMPLETE",
            "CURRENT_BUILD_MANIFEST_QUALIFIED",
            "B05_REAL_CAPITAL_AUTHORIZED",
            "RUNTIME_REAL_WRITE_GATE_OPEN",
        ],
        "current_state": {
            "design_status": "BLOCKED_BY_UPSTREAM_CONFLICT",
            "live_write_build_capability": "NOT_QUALIFIED",
            "b05_construction_eligibility": "BLOCKED",
            "b05_real_capital_eligibility": "BLOCKED",
            "runtime_real_write_gate": "CLOSED",
            "live_write_gate_evidence": empty_live_write_evidence(),
        },
        "runtime_configuration": {
            "live_write_gate_binding": {
                "schema_version": 1,
                "state_fields": [
                    "live_write_build_capability",
                    "b05_real_capital_eligibility",
                    "runtime_real_write_gate",
                ],
                "state_separation_required": True,
                "default_effective_gate": "CLOSED",
                "location": "DETACHED_OUTSIDE_REPOSITORY_AND_BUILDMANIFEST",
                "nonsecret": True,
                "eligibility_binding_inputs": [
                    "final_build_manifest_digest",
                    "user_authorization_ref",
                    "account_capital_limit_version_ref",
                ],
                "open_gate_binding_inputs": [
                    "machine_authorization_version_ref",
                    "plan_allocation_ref",
                ],
                "phase_order": [
                    "B05_REAL_CAPITAL_ELIGIBILITY_CLOSED",
                    "EXISTING_ACTIVATION_RUNTIME_OPEN",
                ],
                "eligibility_scope": "EXACT_ONE_ACCOUNT_CAPITAL_LIMIT_VERSION",
                "open_gate_scope": "EXACT_ONE_EXISTING_ACTIVATION",
                "closed_binding_activation_refs": "FORBIDDEN",
                "open_binding_activation_refs": "REQUIRED",
                "file_security_profile": "WINDOWS_PROTECTED_EXACT_DACL_V1",
                "credential_resolution_order": "DATABASE_GATE_BEFORE_BINANCE_SECRETS",
            }
        },
        "formalization_record": {
            "status": "BLOCKED_BY_UPSTREAM_CONFLICT",
            "alignment": "NOT_FULLY_ALIGNED_UPSTREAM",
            "conflicts": [{"id": "EXAMPLE"}],
        },
        "design_formalization_gate": {"status": "BLOCKED"},
        "dependency_qualification_gate": {"status": "IN_PROGRESS"},
        "construction_packages": packages,
        "definition_of_ready_to_start_p0": {
            "design_status": "BLOCKED_BY_UPSTREAM_CONFLICT"
        },
    }


def aligned_b00_to_b04_complete_plan() -> dict[str, object]:
    plan = deepcopy(unresolved_blocked_plan())
    plan["current_state"]["design_status"] = "ALIGNED"
    plan["current_state"]["live_write_build_capability"] = "QUALIFIED"
    plan["formalization_record"] = {
        "status": "ALIGNED",
        "alignment": "ALIGNED",
        "conflicts": [{"id": "EXAMPLE", "resolution_status": "RESOLVED"}],
    }
    plan["design_formalization_gate"]["status"] = "ALIGNED"
    plan["dependency_qualification_gate"]["status"] = "QUALIFIED"
    plan["definition_of_ready_to_start_p0"]["design_status"] = "READY"
    for package_id in ("B01", "B02", "B03", "B04"):
        plan["construction_packages"][package_id]["status"] = "COMPLETED"
        plan["construction_packages"][package_id]["eligibility"] = "ELIGIBLE"
    qualify_b04_observations(plan)
    return plan


def authorized_live_write_evidence() -> dict[str, object]:
    return {
        "observed_at": "2026-07-17T09:00:00+08:00",
        "build_manifest_digest": "sha256:" + "a" * 64,
        "user_authorization_ref": "authorization://owner/decision-1",
        "account_capital_limit_version_ref": "cap://account-limit/1",
        "machine_authorization_version_ref": None,
        "plan_allocation_ref": None,
        "authorized_activation_id": None,
    }


def bind_existing_activation(plan: dict[str, object]) -> None:
    plan["current_state"]["live_write_gate_evidence"].update(
        {
            "machine_authorization_version_ref": "cap://machine-auth/1",
            "plan_allocation_ref": "cap://plan-allocation/1",
            "authorized_activation_id": "tradeplan://activation/1",
        }
    )


def aligned_b04_in_progress_plan() -> dict[str, object]:
    plan = aligned_b00_to_b04_complete_plan()
    plan["construction_packages"]["B04"]["status"] = (
        "IN_PROGRESS_CONSTRUCTION_GATE_AND_LONG_OBSERVATION"
    )
    plan["construction_packages"]["B04"].update(b04_observation_records())
    plan["current_state"]["live_write_build_capability"] = "NOT_QUALIFIED"
    return plan


def add_research_track(plan: dict[str, object]) -> dict[str, object]:
    plan["research_build_order"] = ["R00", "R01", "R02", "R03"]
    plan["construction_packages"].update(
        {
            "R00": {
                "eligibility": "BLOCKED_UNTIL_PACKAGE_CONTRACT_FROZEN",
                "status": "NOT_STARTED",
                "depends_on": [],
            },
            "R01": {
                "eligibility": "BLOCKED_UNTIL_R00_COMPLETE",
                "status": "NOT_STARTED",
                "depends_on": ["R00"],
            },
            "R02": {
                "eligibility": "BLOCKED_UNTIL_R01_COMPLETE_AND_POLICY_FROZEN",
                "status": "NOT_STARTED",
                "depends_on": ["R01"],
            },
            "R03": {
                "eligibility": "NOT_AUTHORIZED",
                "status": "NOT_STARTED",
                "depends_on": ["R02", "B05", "V01"],
            },
        }
    )
    plan["research_track"] = {
        "owner_authorization": {
            "status": "AUTHORIZED",
            "decision_ref": "OWNER-DIRECTION-20260718-R00-INDEPENDENT-START",
        },
        "research_policy": {"status": "NOT_FROZEN"},
        "owner_selected_evidence_ref": None,
        "runtime_overlap": {
            "qualification": "NOT_QUALIFIED",
            "execution_state": "STOPPED",
        },
        "preexisting_data_boundary": {
            "confirmation_eligible_not_before": None,
        },
        "r00_r02_effects": {
            "p0_build_order": "NONE",
            "b01_b05_scope_dependency_status_evidence": "NONE",
            "live_write_build_capability": "NONE",
            "b05_construction_eligibility": "NONE",
            "b05_real_capital_eligibility": "NONE",
            "runtime_real_write_gate": "NONE",
            "product_database_or_migration": "NONE",
            "product_process_or_write_path": "NONE",
            "product_release_group": "NONE",
        },
    }
    plan["value_decision_gate"] = {"status": "NOT_STARTED"}
    return plan


def bind_research_package_contract(
    plan: dict[str, object],
    package_id: str,
    *,
    completed: bool = False,
) -> None:
    package = plan["construction_packages"][package_id]
    package.update(
        {
            "id": package_id,
            "contract_state": "FROZEN",
            "semantic_scopes": [
                {
                    "owner": "HALPHA-ALP-003@v0.3.0",
                    "anchor": "ALP-RSCH-BND-001-REQ",
                }
            ],
            "base_revision": "a" * 40,
            "owned_paths": [f"research/{package_id.lower()}/**"],
            "contracts": {
                "inputs": [
                    {
                        "ref": "accepted_design_set_and_basis",
                        "identity": "sha256:" + "b" * 64,
                    }
                ],
                "outputs": [{"ref": f"{package_id.lower()}_output"}],
            },
            "effects": {
                "migration": "NONE",
                "runtime": "NONE",
                "release": "NONE",
                "authority": "NONE",
                "credential": "NONE",
            },
            "integration_gate": "SELECTIVE_VALIDATION_AND_PATH_OWNERSHIP",
            "exit_evidence": {
                "requirements": ["qualified evidence"],
                "output_revision": "c" * 40 if completed else None,
            },
        }
    )


class ConstructionPlanGovernanceTests(unittest.TestCase):
    def assert_has_code(self, plan: dict[str, object], code: str) -> None:
        codes = {violation.code for violation in validate_plan(plan)}
        self.assertIn(code, codes)

    def test_allows_isolated_b00_while_conflicts_block_downstream(self) -> None:
        self.assertEqual(validate_plan(unresolved_blocked_plan()), [])

    def test_rejects_accepted_design_set_basis_drift(self) -> None:
        plan = unresolved_blocked_plan()
        plan["accepted_design_set"] = {
            "upper_level": ["HALPHA-CON-001@v1.0.0"],
            "l2_revisions": ["HALPHA-CAP-001@v1.0.0"],
            "l3": [],
        }
        plan["basis"] = {
            "accepted": [
                "HALPHA-CON-001@v1.0.0",
                "HALPHA-ALP-001@v1.0.0",
            ]
        }
        self.assert_has_code(plan, "GOV-DESIGN-SET-002")

    def test_rejects_ready_state_with_unresolved_conflicts(self) -> None:
        plan = unresolved_blocked_plan()
        plan["current_state"]["design_status"] = "READY"
        plan["design_formalization_gate"]["status"] = "ACCEPTED_FOR_B00"
        plan["definition_of_ready_to_start_p0"]["design_status"] = "READY"
        self.assert_has_code(plan, "GOV-CONFLICT-001")

    def test_requires_formalization_record_itself_to_be_blocked(self) -> None:
        plan = unresolved_blocked_plan()
        plan["formalization_record"]["status"] = (
            "ACCEPTED_WITH_RECORDED_UPSTREAM_CONFLICTS"
        )
        self.assert_has_code(plan, "GOV-CONFLICT-001")

    def test_rejects_unblocked_downstream_package_during_conflict(self) -> None:
        plan = unresolved_blocked_plan()
        del plan["construction_packages"]["B03"]["eligibility"]
        self.assert_has_code(plan, "GOV-CONFLICT-002")

    def test_requires_runtime_gate_closed_during_conflict(self) -> None:
        plan = unresolved_blocked_plan()
        plan["current_state"]["runtime_real_write_gate"] = "OPEN"
        self.assert_has_code(plan, "GOV-CONFLICT-003")

    def test_requires_both_b01_dependencies(self) -> None:
        plan = unresolved_blocked_plan()
        plan["construction_packages"]["B01"]["depends_on"] = ["B00=QUALIFIED"]
        self.assert_has_code(plan, "GOV-DEPENDENCY-002")

    def test_requires_each_downstream_dependency(self) -> None:
        plan = unresolved_blocked_plan()
        plan["construction_packages"]["B04"]["depends_on"] = ["B02"]
        self.assert_has_code(plan, "GOV-DEPENDENCY-003")

    def test_rejects_downstream_progress_before_b00_qualified(self) -> None:
        for status in ("STARTED", "IN_PROGRESS", "COMPLETE", "UNRECOGNIZED_ACTIVE"):
            with self.subTest(status=status):
                plan = unresolved_blocked_plan()
                plan["construction_packages"]["B02"]["status"] = status
                self.assert_has_code(plan, "GOV-SEQUENCE-001")

    def test_rejects_downstream_progress_before_d00_aligned(self) -> None:
        plan = unresolved_blocked_plan()
        plan["dependency_qualification_gate"]["status"] = "QUALIFIED"
        plan["construction_packages"]["B01"]["status"] = "IN_PROGRESS"
        self.assert_has_code(plan, "GOV-SEQUENCE-002")

    def test_rejects_downstream_progress_while_eligibility_blocked(self) -> None:
        plan = unresolved_blocked_plan()
        plan["formalization_record"] = {
            "status": "ALIGNED",
            "alignment": "ALIGNED",
            "conflicts": [{"id": "EXAMPLE", "resolution_status": "RESOLVED"}],
        }
        plan["design_formalization_gate"]["status"] = "ALIGNED"
        plan["dependency_qualification_gate"]["status"] = "QUALIFIED"
        plan["construction_packages"]["B01"]["status"] = "IN_PROGRESS"
        self.assert_has_code(plan, "GOV-SEQUENCE-003")

    def test_rejects_package_progress_before_direct_dependency_complete(self) -> None:
        plan = aligned_b00_to_b04_complete_plan()
        del plan["construction_packages"]["B02"]["status"]
        plan["construction_packages"]["B03"]["status"] = "IN_PROGRESS"
        self.assert_has_code(plan, "GOV-SEQUENCE-004")

    def test_rejects_unknown_live_gate_enum(self) -> None:
        plan = unresolved_blocked_plan()
        plan["current_state"]["live_write_build_capability"] = "MAYBE"
        self.assert_has_code(plan, "GOV-LIVE-GATE-001")

    def test_rejects_deprecated_combined_real_write_field(self) -> None:
        plan = unresolved_blocked_plan()
        plan["current_state"]["real_write_status"] = "DISABLED"
        self.assert_has_code(plan, "GOV-LIVE-GATE-002")

    def test_rejects_live_gate_wiring_that_can_resolve_secrets_before_database_gate(self) -> None:
        plan = unresolved_blocked_plan()
        plan["runtime_configuration"]["live_write_gate_binding"][
            "credential_resolution_order"
        ] = "BINANCE_SECRETS_BEFORE_DATABASE_GATE"
        self.assert_has_code(plan, "GOV-LIVE-GATE-003")

    def test_rejects_build_capability_before_b01_b04_complete(self) -> None:
        plan = unresolved_blocked_plan()
        plan["formalization_record"] = {
            "status": "ALIGNED",
            "alignment": "ALIGNED",
            "conflicts": [{"id": "EXAMPLE", "resolution_status": "RESOLVED"}],
        }
        plan["design_formalization_gate"]["status"] = "ALIGNED"
        plan["dependency_qualification_gate"]["status"] = "QUALIFIED"
        plan["current_state"]["live_write_build_capability"] = "QUALIFIED"
        self.assert_has_code(plan, "GOV-REAL-WRITE-001")

    def test_rejects_open_gate_when_b05_not_authorized_or_started(self) -> None:
        plan = aligned_b00_to_b04_complete_plan()
        plan["current_state"]["runtime_real_write_gate"] = "OPEN"
        plan["current_state"]["live_write_gate_evidence"] = (
            authorized_live_write_evidence()
        )
        self.assert_has_code(plan, "GOV-REAL-WRITE-004")

    def test_rejects_b05_construction_authorization_mismatch(self) -> None:
        plan = aligned_b00_to_b04_complete_plan()
        plan["current_state"]["b05_construction_eligibility"] = "AUTHORIZED"
        self.assert_has_code(plan, "GOV-B05-CONSTRUCTION-002")

    def test_rejects_b05_real_capital_authorization_without_bound_evidence(self) -> None:
        plan = aligned_b00_to_b04_complete_plan()
        authorize_b05_real_capital(plan)
        plan["current_state"]["live_write_gate_evidence"] = empty_live_write_evidence()
        self.assert_has_code(plan, "GOV-REAL-WRITE-005")

    def test_rejects_b05_real_capital_without_qualified_build_capability(self) -> None:
        plan = aligned_b00_to_b04_complete_plan()
        authorize_b05_real_capital(plan)
        plan["current_state"]["live_write_build_capability"] = "NOT_QUALIFIED"
        self.assert_has_code(plan, "GOV-REAL-WRITE-002")

    def test_rejects_open_gate_without_bound_evidence(self) -> None:
        plan = aligned_b00_to_b04_complete_plan()
        authorize_b05_real_capital(plan)
        plan["current_state"]["runtime_real_write_gate"] = "OPEN"
        plan["construction_packages"]["B05"]["status"] = "IN_PROGRESS"
        plan["current_state"]["live_write_gate_evidence"] = empty_live_write_evidence()
        self.assert_has_code(plan, "GOV-REAL-WRITE-005")

    def test_requires_b05_in_progress_while_runtime_gate_is_open(self) -> None:
        plan = aligned_b00_to_b04_complete_plan()
        authorize_b05_real_capital(plan)
        bind_existing_activation(plan)
        plan["current_state"]["runtime_real_write_gate"] = "OPEN"
        plan["construction_packages"]["B05"]["status"] = "COMPLETED"
        self.assert_has_code(plan, "GOV-REAL-WRITE-004")

    def test_rejects_malformed_bound_manifest_digest(self) -> None:
        plan = aligned_b00_to_b04_complete_plan()
        authorize_b05_real_capital(plan)
        bind_existing_activation(plan)
        plan["current_state"]["runtime_real_write_gate"] = "OPEN"
        plan["construction_packages"]["B05"]["status"] = "IN_PROGRESS"
        plan["current_state"]["live_write_gate_evidence"]["build_manifest_digest"] = (
            "sha256:not-a-digest"
        )
        self.assert_has_code(plan, "GOV-REAL-WRITE-006")

    def test_allows_open_gate_only_after_full_b05_authorization(self) -> None:
        plan = aligned_b00_to_b04_complete_plan()
        authorize_b05_real_capital(plan)
        bind_existing_activation(plan)
        plan["current_state"]["runtime_real_write_gate"] = "OPEN"
        plan["construction_packages"]["B05"]["status"] = "IN_PROGRESS"
        self.assertEqual(validate_plan(plan), [])

    def test_allows_b05_construction_while_long_observation_continues(self) -> None:
        plan = aligned_b04_in_progress_plan()
        qualify_b04_observations(plan, long_status="IN_PROGRESS")
        authorize_b05_construction(plan)
        plan["construction_packages"]["B05"]["status"] = "IN_PROGRESS"
        self.assertEqual(validate_plan(plan), [])

    def test_rejects_b05_construction_before_continuation_gate(self) -> None:
        plan = aligned_b04_in_progress_plan()
        authorize_b05_construction(plan)
        plan["construction_packages"]["B05"]["status"] = "IN_PROGRESS"
        self.assert_has_code(plan, "GOV-B05-CONSTRUCTION-003")

    def test_rejects_real_capital_while_long_observation_continues(self) -> None:
        plan = aligned_b04_in_progress_plan()
        qualify_b04_observations(plan, long_status="IN_PROGRESS")
        authorize_b05_real_capital(plan)
        self.assert_has_code(plan, "GOV-REAL-WRITE-002")

    def test_long_observation_failure_does_not_erase_b05_construction(self) -> None:
        plan = aligned_b04_in_progress_plan()
        qualify_b04_observations(plan, long_status="REJECTED")
        authorize_b05_construction(plan)
        plan["construction_packages"]["B05"]["status"] = "IN_PROGRESS"
        self.assertEqual(validate_plan(plan), [])

    def test_rejects_pending_continuation_gate_at_hard_deadline(self) -> None:
        plan = aligned_b04_in_progress_plan()
        violations = validate_plan(
            plan,
            now=datetime(2099, 1, 2, tzinfo=timezone.utc),
        )
        self.assertIn("GOV-CONTINUATION-TIME-003", {item.code for item in violations})

    def test_rejects_qualified_continuation_gate_before_eight_hours(self) -> None:
        plan = aligned_b04_in_progress_plan()
        qualify_b04_observations(plan, long_status="IN_PROGRESS")
        plan["construction_packages"]["B04"]["construction_continuation_gate"][
            "current_evidence"
        ]["windows_awake_identity_hours"] = 7.99
        self.assert_has_code(plan, "GOV-CONTINUATION-QUALIFICATION-001")

    def test_rejects_future_continuation_gate_evidence(self) -> None:
        plan = aligned_b04_in_progress_plan()
        qualify_b04_observations(plan, long_status="IN_PROGRESS")
        plan["construction_packages"]["B04"]["construction_continuation_gate"][
            "current_evidence"
        ]["observed_at"] = "2099-01-01T08:00:00Z"
        self.assert_has_code(plan, "GOV-CONTINUATION-QUALIFICATION-001")

    def test_requires_bound_continuation_gate_evidence(self) -> None:
        plan = aligned_b04_in_progress_plan()
        del plan["construction_packages"]["B04"]["construction_continuation_gate"][
            "current_evidence"
        ]["evidence_digest"]
        self.assert_has_code(plan, "GOV-CONTINUATION-EVIDENCE-001")

    def test_preserves_b05_construction_only_permissions(self) -> None:
        plan = aligned_b04_in_progress_plan()
        plan["construction_packages"]["B05"]["construction_eligibility"][
            "permits"
        ].append("LIVE_WRITE_CREDENTIAL_LOAD")
        self.assert_has_code(plan, "GOV-B05-CONSTRUCTION-001")

    def test_requires_b05_real_capital_package_bindings(self) -> None:
        plan = aligned_b00_to_b04_complete_plan()
        authorize_b05_real_capital(plan)
        plan["construction_packages"]["B05"]["real_capital_eligibility"][
            "account_capital_limit_version_ref"
        ] = None
        self.assert_has_code(plan, "GOV-B05-REAL-CAPITAL-004")

    def test_rejects_b05_capital_scope_not_bound_to_live_gate(self) -> None:
        plan = aligned_b00_to_b04_complete_plan()
        authorize_b05_real_capital(plan)
        plan["construction_packages"]["B05"]["real_capital_eligibility"][
            "account_capital_limit_version_ref"
        ] = "cap://unrelated-account-limit"
        self.assert_has_code(plan, "GOV-B05-REAL-CAPITAL-004")

    def test_allows_real_capital_eligibility_before_activation_refs_exist(self) -> None:
        plan = aligned_b00_to_b04_complete_plan()
        authorize_b05_real_capital(plan)

        self.assertEqual(validate_plan(plan), [])

    def test_rejects_open_gate_before_existing_activation_refs_are_bound(self) -> None:
        plan = aligned_b00_to_b04_complete_plan()
        authorize_b05_real_capital(plan)
        plan["current_state"]["runtime_real_write_gate"] = "OPEN"
        plan["construction_packages"]["B05"]["status"] = "IN_PROGRESS"

        self.assert_has_code(plan, "GOV-REAL-WRITE-005")

    def test_rejects_invalid_real_capital_evidence_time(self) -> None:
        plan = aligned_b00_to_b04_complete_plan()
        authorize_b05_real_capital(plan)
        plan["current_state"]["live_write_gate_evidence"]["observed_at"] = "not-a-time"
        self.assert_has_code(plan, "GOV-TIME-001")

    def test_rejects_future_real_capital_evidence_time(self) -> None:
        plan = aligned_b00_to_b04_complete_plan()
        authorize_b05_real_capital(plan)
        plan["current_state"]["live_write_gate_evidence"]["observed_at"] = (
            "2099-01-01T00:00:00Z"
        )
        self.assert_has_code(plan, "GOV-REAL-WRITE-EVIDENCE-001")

    def test_rejects_long_observation_status_without_child_evidence(self) -> None:
        plan = aligned_b00_to_b04_complete_plan()
        long_observation = plan["construction_packages"]["B04"]["long_observation"]
        long_observation["windows_awake_runtime"]["status"] = "IN_PROGRESS"
        long_observation["windows_awake_runtime"]["awake_elapsed_hours"] = 1.0
        long_observation["live_read_only_market"]["status"] = "IN_PROGRESS"
        long_observation["live_read_only_market"]["observed_natural_days"] = 1
        self.assert_has_code(plan, "GOV-LONG-OBSERVATION-QUALIFICATION-001")

    def test_rejects_long_observation_without_bound_digests(self) -> None:
        plan = aligned_b00_to_b04_complete_plan()
        plan["construction_packages"]["B04"]["long_observation"][
            "live_read_only_market"
        ]["evidence_digest"] = None
        self.assert_has_code(plan, "GOV-LONG-OBSERVATION-EVIDENCE-001")

    def test_rejects_long_observation_bound_to_another_baseline(self) -> None:
        plan = aligned_b00_to_b04_complete_plan()
        plan["construction_packages"]["B04"]["long_observation"][
            "frozen_baseline_ref"
        ] = "unrelated://baseline"
        self.assert_has_code(plan, "GOV-LONG-OBSERVATION-BASELINE-001")

    def test_rejects_live_read_only_overlapping_windows_observation(self) -> None:
        plan = aligned_b00_to_b04_complete_plan()
        plan["construction_packages"]["B04"]["long_observation"][
            "live_read_only_market"
        ].update(
            {
                "started_at": "2026-01-03T00:00:00Z",
                "qualified_at": "2026-01-10T00:00:00Z",
            }
        )
        self.assert_has_code(plan, "GOV-LONG-OBSERVATION-SEQUENCE-001")

    def test_rejects_early_windows_child_qualification_while_parent_in_progress(self) -> None:
        plan = aligned_b04_in_progress_plan()
        windows = plan["construction_packages"]["B04"]["long_observation"][
            "windows_awake_runtime"
        ]
        windows["status"] = "QUALIFIED"
        windows["awake_elapsed_hours"] = 1.0
        self.assert_has_code(plan, "GOV-LONG-OBSERVATION-QUALIFICATION-001")

    def test_rejects_early_live_child_qualification_while_parent_in_progress(self) -> None:
        plan = aligned_b04_in_progress_plan()
        long_observation = plan["construction_packages"]["B04"]["long_observation"]
        windows = long_observation["windows_awake_runtime"]
        windows.update(
            {
                "status": "QUALIFIED",
                "latest_checkpoint_at": "2026-01-04T00:00:00Z",
                "awake_elapsed_hours": 72.0,
            }
        )
        live_read_only = long_observation["live_read_only_market"]
        live_read_only.update(
            {
                "status": "QUALIFIED",
                "started_at": "2026-01-04T00:00:00Z",
                "qualified_at": "2026-01-05T00:00:00Z",
                "observed_natural_days": 1,
                "evidence_digest": "sha256:" + "1" * 64,
            }
        )
        self.assert_has_code(plan, "GOV-LONG-OBSERVATION-QUALIFICATION-001")

    def test_allows_live_child_to_start_after_windows_child_qualifies(self) -> None:
        plan = aligned_b04_in_progress_plan()
        long_observation = plan["construction_packages"]["B04"]["long_observation"]
        long_observation["windows_awake_runtime"].update(
            {
                "status": "QUALIFIED",
                "latest_checkpoint_at": "2026-01-04T00:00:00Z",
                "awake_elapsed_hours": 72.0,
            }
        )
        long_observation["live_read_only_market"].update(
            {
                "status": "IN_PROGRESS",
                "started_at": "2026-01-04T00:00:00Z",
                "evidence_digest": "sha256:" + "1" * 64,
            }
        )
        self.assertEqual(validate_plan(plan), [])

    def test_allows_planned_research_while_b04_is_in_progress(self) -> None:
        plan = add_research_track(aligned_b04_in_progress_plan())
        self.assertEqual(validate_plan(plan), [])

    def test_preserves_p0_build_order(self) -> None:
        plan = add_research_track(aligned_b04_in_progress_plan())
        plan["build_order"] = [
            "D00",
            "B00",
            "B01",
            "B03",
            "B02",
            "B04_CONSTRUCTION_CONTINUATION_GATE",
            "B05_CONSTRUCTION",
        ]
        self.assert_has_code(plan, "GOV-BUILD-ORDER-001")

    def test_preserves_release_and_real_capital_order(self) -> None:
        plan = aligned_b04_in_progress_plan()
        plan["release_and_real_capital_order"] = [
            "B04_LONG_OBSERVATION",
            "CURRENT_BUILD_MANIFEST_QUALIFIED",
            "B04_COMPLETE",
            "B05_REAL_CAPITAL_AUTHORIZED",
            "RUNTIME_REAL_WRITE_GATE_OPEN",
        ]
        self.assert_has_code(plan, "GOV-BUILD-ORDER-002")

    def test_rejects_research_dependency_or_order_drift(self) -> None:
        plan = add_research_track(aligned_b04_in_progress_plan())
        plan["construction_packages"]["R02"]["depends_on"] = ["R03"]
        self.assert_has_code(plan, "GOV-RESEARCH-DAG-001")
        self.assert_has_code(plan, "GOV-RESEARCH-DAG-002")

    def test_allows_r00_while_b04_is_in_progress(self) -> None:
        plan = add_research_track(aligned_b04_in_progress_plan())
        bind_research_package_contract(plan, "R00")
        plan["construction_packages"]["R00"]["eligibility"] = "ELIGIBLE"
        plan["construction_packages"]["R00"]["status"] = "IN_PROGRESS"
        self.assertEqual(validate_plan(plan), [])

    def test_allows_r01_to_start_while_b04_is_in_progress(self) -> None:
        plan = add_research_track(aligned_b04_in_progress_plan())
        bind_research_package_contract(plan, "R00", completed=True)
        plan["construction_packages"]["R00"]["eligibility"] = "ELIGIBLE"
        plan["construction_packages"]["R00"]["status"] = "COMPLETED"
        bind_research_package_contract(plan, "R01")
        plan["construction_packages"]["R01"]["eligibility"] = "ELIGIBLE"
        plan["construction_packages"]["R01"]["status"] = "IN_PROGRESS"
        self.assertEqual(validate_plan(plan), [])

    def test_rejects_r01_completion_before_b04_and_boundary_freeze(self) -> None:
        plan = add_research_track(aligned_b04_in_progress_plan())
        for package_id in ("R00", "R01"):
            bind_research_package_contract(plan, package_id, completed=True)
            plan["construction_packages"][package_id]["eligibility"] = "ELIGIBLE"
            plan["construction_packages"][package_id]["status"] = "COMPLETED"
        plan["research_track"]["research_policy"]["status"] = "FROZEN"
        self.assert_has_code(plan, "GOV-RESEARCH-R01-001")

    def test_allows_r01_completion_after_b04_and_boundary_freeze(self) -> None:
        plan = add_research_track(aligned_b00_to_b04_complete_plan())
        for package_id in ("R00", "R01"):
            bind_research_package_contract(plan, package_id, completed=True)
            plan["construction_packages"][package_id]["eligibility"] = "ELIGIBLE"
            plan["construction_packages"][package_id]["status"] = "COMPLETED"
        plan["research_track"]["research_policy"]["status"] = "FROZEN"
        plan["research_track"]["preexisting_data_boundary"][
            "confirmation_eligible_not_before"
        ] = "2026-07-19T00:00:00Z"
        self.assertEqual(validate_plan(plan), [])

    def test_rejects_r00_eligibility_without_frozen_package_contract(self) -> None:
        plan = add_research_track(aligned_b00_to_b04_complete_plan())
        plan["construction_packages"]["R00"]["eligibility"] = "ELIGIBLE"
        self.assert_has_code(plan, "GOV-RESEARCH-CONTRACT-001")
        self.assert_has_code(plan, "GOV-RESEARCH-CONTRACT-002")

    def test_rejects_unknown_research_eligibility_fail_closed(self) -> None:
        plan = add_research_track(aligned_b00_to_b04_complete_plan())
        plan["construction_packages"]["R00"]["eligibility"] = "READY"
        self.assert_has_code(plan, "GOV-RESEARCH-ELIGIBILITY-001")
        self.assert_has_code(plan, "GOV-RESEARCH-CONTRACT-001")

    def test_rejects_completed_package_without_output_revision(self) -> None:
        plan = add_research_track(aligned_b00_to_b04_complete_plan())
        bind_research_package_contract(plan, "R00")
        plan["construction_packages"]["R00"]["eligibility"] = "ELIGIBLE"
        plan["construction_packages"]["R00"]["status"] = "COMPLETED"
        self.assert_has_code(plan, "GOV-RESEARCH-CONTRACT-004")

    def test_rejects_unfrozen_or_unversioned_research_input(self) -> None:
        plan = add_research_track(aligned_b00_to_b04_complete_plan())
        bind_research_package_contract(plan, "R00")
        package = plan["construction_packages"]["R00"]
        package["eligibility"] = "ELIGIBLE"
        package["contract_state"] = "TO_BE_FROZEN_AT_PACKAGE_START"
        package["contracts"]["inputs"][0]["identity"] = "latest"
        self.assert_has_code(plan, "GOV-RESEARCH-CONTRACT-001")

    def test_allows_b05_and_r00_package_progress_together(self) -> None:
        plan = add_research_track(aligned_b00_to_b04_complete_plan())
        authorize_b05_construction(plan)
        plan["construction_packages"]["B05"]["status"] = "IN_PROGRESS"
        bind_research_package_contract(plan, "R00")
        plan["construction_packages"]["R00"]["eligibility"] = "ELIGIBLE"
        plan["construction_packages"]["R00"]["status"] = "IN_PROGRESS"
        self.assertEqual(validate_plan(plan), [])

    def test_rejects_r01_before_r00_complete(self) -> None:
        plan = add_research_track(aligned_b00_to_b04_complete_plan())
        plan["construction_packages"]["R01"]["eligibility"] = "ELIGIBLE"
        plan["construction_packages"]["R01"]["status"] = "IN_PROGRESS"
        self.assert_has_code(plan, "GOV-RESEARCH-SEQUENCE-002")

    def test_rejects_r02_until_policy_is_frozen(self) -> None:
        plan = add_research_track(aligned_b00_to_b04_complete_plan())
        for package_id in ("R00", "R01"):
            plan["construction_packages"][package_id]["eligibility"] = "ELIGIBLE"
            plan["construction_packages"][package_id]["status"] = "COMPLETED"
        plan["construction_packages"]["R02"]["eligibility"] = "ELIGIBLE"
        plan["construction_packages"]["R02"]["status"] = "IN_PROGRESS"
        self.assert_has_code(plan, "GOV-RESEARCH-POLICY-002")

    def test_rejects_nonzero_research_effect(self) -> None:
        plan = add_research_track(aligned_b04_in_progress_plan())
        plan["research_track"]["r00_r02_effects"]["runtime_real_write_gate"] = "CHANGED"
        self.assert_has_code(plan, "GOV-RESEARCH-EFFECT-001")

    def test_rejects_unqualified_research_execution_during_real_write(self) -> None:
        plan = add_research_track(aligned_b00_to_b04_complete_plan())
        authorize_b05_real_capital(plan)
        plan["current_state"]["runtime_real_write_gate"] = "OPEN"
        plan["construction_packages"]["B05"]["status"] = "IN_PROGRESS"
        plan["research_track"]["runtime_overlap"]["execution_state"] = "RUNNING"
        self.assert_has_code(plan, "GOV-RESEARCH-OVERLAP-002")

    def test_rejects_r03_without_all_gates_and_owner_selection(self) -> None:
        plan = add_research_track(aligned_b00_to_b04_complete_plan())
        plan["construction_packages"]["R03"]["eligibility"] = "AUTHORIZED"
        plan["construction_packages"]["R03"]["status"] = "IN_PROGRESS"
        self.assert_has_code(plan, "GOV-RESEARCH-R03-001")

    def test_allows_r03_only_after_all_gates_and_owner_selection(self) -> None:
        plan = add_research_track(aligned_b00_to_b04_complete_plan())
        authorize_b05_real_capital(plan)
        plan["construction_packages"]["B05"]["status"] = "COMPLETED"
        for package_id in ("R00", "R01", "R02"):
            bind_research_package_contract(plan, package_id, completed=True)
            plan["construction_packages"][package_id]["eligibility"] = "ELIGIBLE"
            plan["construction_packages"][package_id]["status"] = "COMPLETED"
        plan["research_track"]["research_policy"]["status"] = "FROZEN"
        plan["research_track"]["preexisting_data_boundary"][
            "confirmation_eligible_not_before"
        ] = "2026-07-19T00:00:00Z"
        plan["research_track"]["owner_selected_evidence_ref"] = (
            "research-evidence://selected/candidate-1"
        )
        plan["value_decision_gate"]["status"] = "COMPLETED"
        bind_research_package_contract(plan, "R03")
        plan["construction_packages"]["R03"]["eligibility"] = "AUTHORIZED"
        plan["construction_packages"]["R03"]["status"] = "IN_PROGRESS"
        self.assertEqual(validate_plan(plan), [])


if __name__ == "__main__":
    unittest.main()
