from __future__ import annotations

from copy import deepcopy
import unittest

from governance.validate_construction_plan import validate_plan


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
        "current_state": {
            "design_status": "BLOCKED_BY_UPSTREAM_CONFLICT",
            "real_write_status": "DISABLED",
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


class ConstructionPlanGovernanceTests(unittest.TestCase):
    def assert_has_code(self, plan: dict[str, object], code: str) -> None:
        codes = {violation.code for violation in validate_plan(plan)}
        self.assertIn(code, codes)

    def test_allows_isolated_b00_while_conflicts_block_downstream(self) -> None:
        self.assertEqual(validate_plan(unresolved_blocked_plan()), [])

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

    def test_requires_real_write_disabled_until_b00_b04_complete(self) -> None:
        plan = unresolved_blocked_plan()
        plan["formalization_record"] = {
            "status": "ALIGNED",
            "alignment": "ALIGNED",
            "conflicts": [{"id": "EXAMPLE", "resolution_status": "RESOLVED"}],
        }
        plan["design_formalization_gate"]["status"] = "ALIGNED"
        plan["dependency_qualification_gate"]["status"] = "QUALIFIED"
        for package_id in ("B01", "B02", "B03"):
            plan["construction_packages"][package_id]["status"] = "COMPLETED"
        plan["current_state"]["real_write_status"] = "ENABLED"
        self.assert_has_code(plan, "GOV-REAL-WRITE-001")

    def test_completed_aligned_chain_may_leave_real_write_to_later_gates(self) -> None:
        plan = deepcopy(unresolved_blocked_plan())
        plan["formalization_record"] = {
            "status": "ALIGNED",
            "alignment": "ALIGNED",
            "conflicts": [{"id": "EXAMPLE", "resolution_status": "RESOLVED"}],
        }
        plan["design_formalization_gate"]["status"] = "ALIGNED"
        plan["dependency_qualification_gate"]["status"] = "QUALIFIED"
        for package_id in ("B01", "B02", "B03", "B04"):
            plan["construction_packages"][package_id]["status"] = "COMPLETED"
            plan["construction_packages"][package_id]["eligibility"] = "ELIGIBLE"
        plan["current_state"]["real_write_status"] = "ENABLED"
        self.assertEqual(validate_plan(plan), [])


if __name__ == "__main__":
    unittest.main()
