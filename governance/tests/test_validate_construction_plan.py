from __future__ import annotations

from copy import deepcopy
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
    }


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
            ("B05", "B04"),
        )
    }
    packages["B01"]["depends_on"] = ["D00=ALIGNED", "B00=QUALIFIED"]
    return {
        "build_order": ["D00", "B00", "B01", "B02", "B03", "B04", "B05"],
        "current_state": {
            "design_status": "BLOCKED_BY_UPSTREAM_CONFLICT",
            "live_write_build_capability": "NOT_QUALIFIED",
            "b05_package_eligibility": "NOT_AUTHORIZED",
            "runtime_real_write_gate": "CLOSED",
            "live_write_gate_evidence": empty_live_write_evidence(),
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
    plan["construction_packages"]["B05"]["eligibility"] = (
        "BLOCKED_UNTIL_OWNER_AUTHORIZATION"
    )
    return plan


def authorized_live_write_evidence() -> dict[str, str]:
    return {
        "observed_at": "2026-07-17T09:00:00+08:00",
        "build_manifest_digest": "sha256:" + "a" * 64,
        "user_authorization_ref": "authorization://owner/decision-1",
        "account_capital_limit_version_ref": "cap://account-limit/1",
        "machine_authorization_version_ref": "cap://machine-auth/1",
        "plan_allocation_ref": "cap://plan-allocation/1",
    }


def aligned_b04_in_progress_plan() -> dict[str, object]:
    plan = aligned_b00_to_b04_complete_plan()
    plan["construction_packages"]["B04"]["status"] = "IN_PROGRESS"
    plan["construction_packages"]["B05"]["eligibility"] = "BLOCKED_UNTIL_B04_COMPLETE"
    plan["current_state"]["live_write_build_capability"] = "NOT_QUALIFIED"
    return plan


def add_research_track(plan: dict[str, object]) -> dict[str, object]:
    plan["research_build_order"] = ["R00", "R01", "R02", "R03"]
    plan["construction_packages"].update(
        {
            "R00": {
                "eligibility": "BLOCKED_UNTIL_B04_COMPLETE",
                "status": "NOT_STARTED",
                "depends_on": ["B04"],
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
            "status": "AUTHORIZED_CONDITIONAL_ON_B04_COMPLETE",
            "decision_ref": "OWNER-DIRECTION-20260718-PARALLEL-RESEARCH",
        },
        "research_policy": {"status": "NOT_FROZEN"},
        "owner_selected_evidence_ref": None,
        "runtime_overlap": {
            "qualification": "NOT_QUALIFIED",
            "execution_state": "STOPPED",
        },
        "r00_r02_effects": {
            "p0_build_order": "NONE",
            "b01_b05_scope_dependency_status_evidence": "NONE",
            "live_write_build_capability": "NONE",
            "b05_package_eligibility": "NONE",
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

    def test_rejects_b05_authorization_mismatch(self) -> None:
        plan = aligned_b00_to_b04_complete_plan()
        plan["current_state"]["b05_package_eligibility"] = "AUTHORIZED"
        self.assert_has_code(plan, "GOV-REAL-WRITE-003")

    def test_rejects_b05_authorization_without_bound_evidence(self) -> None:
        plan = aligned_b00_to_b04_complete_plan()
        plan["current_state"]["b05_package_eligibility"] = "AUTHORIZED"
        plan["construction_packages"]["B05"]["eligibility"] = "AUTHORIZED"
        self.assert_has_code(plan, "GOV-REAL-WRITE-005")

    def test_rejects_b05_authorization_without_qualified_build_capability(self) -> None:
        plan = aligned_b00_to_b04_complete_plan()
        plan["current_state"]["live_write_build_capability"] = "NOT_QUALIFIED"
        plan["current_state"]["b05_package_eligibility"] = "AUTHORIZED"
        plan["current_state"]["live_write_gate_evidence"] = (
            authorized_live_write_evidence()
        )
        plan["construction_packages"]["B05"]["eligibility"] = "AUTHORIZED"
        self.assert_has_code(plan, "GOV-REAL-WRITE-002")

    def test_rejects_open_gate_without_bound_evidence(self) -> None:
        plan = aligned_b00_to_b04_complete_plan()
        plan["current_state"]["b05_package_eligibility"] = "AUTHORIZED"
        plan["current_state"]["runtime_real_write_gate"] = "OPEN"
        plan["construction_packages"]["B05"]["eligibility"] = "AUTHORIZED"
        plan["construction_packages"]["B05"]["status"] = "IN_PROGRESS"
        self.assert_has_code(plan, "GOV-REAL-WRITE-005")

    def test_requires_b05_in_progress_while_runtime_gate_is_open(self) -> None:
        plan = aligned_b00_to_b04_complete_plan()
        plan["current_state"]["b05_package_eligibility"] = "AUTHORIZED"
        plan["current_state"]["runtime_real_write_gate"] = "OPEN"
        plan["current_state"]["live_write_gate_evidence"] = (
            authorized_live_write_evidence()
        )
        plan["construction_packages"]["B05"]["eligibility"] = "AUTHORIZED"
        plan["construction_packages"]["B05"]["status"] = "COMPLETED"
        self.assert_has_code(plan, "GOV-REAL-WRITE-004")

    def test_rejects_malformed_bound_manifest_digest(self) -> None:
        plan = aligned_b00_to_b04_complete_plan()
        plan["current_state"]["b05_package_eligibility"] = "AUTHORIZED"
        plan["current_state"]["runtime_real_write_gate"] = "OPEN"
        plan["construction_packages"]["B05"]["eligibility"] = "AUTHORIZED"
        plan["construction_packages"]["B05"]["status"] = "IN_PROGRESS"
        plan["current_state"]["live_write_gate_evidence"] = (
            authorized_live_write_evidence()
        )
        plan["current_state"]["live_write_gate_evidence"]["build_manifest_digest"] = (
            "sha256:not-a-digest"
        )
        self.assert_has_code(plan, "GOV-REAL-WRITE-006")

    def test_allows_open_gate_only_after_full_b05_authorization(self) -> None:
        plan = aligned_b00_to_b04_complete_plan()
        plan["current_state"]["b05_package_eligibility"] = "AUTHORIZED"
        plan["current_state"]["runtime_real_write_gate"] = "OPEN"
        plan["current_state"]["live_write_gate_evidence"] = (
            authorized_live_write_evidence()
        )
        plan["construction_packages"]["B05"]["eligibility"] = "AUTHORIZED"
        plan["construction_packages"]["B05"]["status"] = "IN_PROGRESS"
        self.assertEqual(validate_plan(plan), [])

    def test_allows_planned_research_while_b04_is_in_progress(self) -> None:
        plan = add_research_track(aligned_b04_in_progress_plan())
        self.assertEqual(validate_plan(plan), [])

    def test_preserves_p0_build_order(self) -> None:
        plan = add_research_track(aligned_b04_in_progress_plan())
        plan["build_order"] = ["D00", "B00", "B01", "B02", "B04", "B03", "B05"]
        self.assert_has_code(plan, "GOV-BUILD-ORDER-001")

    def test_rejects_research_dependency_or_order_drift(self) -> None:
        plan = add_research_track(aligned_b04_in_progress_plan())
        plan["construction_packages"]["R02"]["depends_on"] = ["R03"]
        self.assert_has_code(plan, "GOV-RESEARCH-DAG-001")
        self.assert_has_code(plan, "GOV-RESEARCH-DAG-002")

    def test_rejects_r00_before_b04_complete(self) -> None:
        plan = add_research_track(aligned_b04_in_progress_plan())
        bind_research_package_contract(plan, "R00")
        plan["construction_packages"]["R00"]["eligibility"] = "ELIGIBLE"
        plan["construction_packages"]["R00"]["status"] = "IN_PROGRESS"
        self.assert_has_code(plan, "GOV-RESEARCH-SEQUENCE-002")

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
        plan["current_state"]["b05_package_eligibility"] = "AUTHORIZED"
        plan["current_state"]["live_write_gate_evidence"] = (
            authorized_live_write_evidence()
        )
        plan["construction_packages"]["B05"]["eligibility"] = "AUTHORIZED"
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
        plan["current_state"]["b05_package_eligibility"] = "AUTHORIZED"
        plan["current_state"]["runtime_real_write_gate"] = "OPEN"
        plan["current_state"]["live_write_gate_evidence"] = (
            authorized_live_write_evidence()
        )
        plan["construction_packages"]["B05"]["eligibility"] = "AUTHORIZED"
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
        plan["current_state"]["b05_package_eligibility"] = "AUTHORIZED"
        plan["current_state"]["live_write_gate_evidence"] = (
            authorized_live_write_evidence()
        )
        plan["construction_packages"]["B05"]["eligibility"] = "AUTHORIZED"
        plan["construction_packages"]["B05"]["status"] = "COMPLETED"
        for package_id in ("R00", "R01", "R02"):
            bind_research_package_contract(plan, package_id, completed=True)
            plan["construction_packages"][package_id]["eligibility"] = "ELIGIBLE"
            plan["construction_packages"][package_id]["status"] = "COMPLETED"
        plan["research_track"]["research_policy"]["status"] = "FROZEN"
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
