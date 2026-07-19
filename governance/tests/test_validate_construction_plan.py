from __future__ import annotations

import unittest

from governance.validate_construction_plan import validate_plan


def current_plan() -> dict[str, object]:
    return {
        "schema_version": 3,
        "document_id": "HALPHA-PLAN-001",
        "level": "L4",
        "current_facts": {
            "runtime": {
                "real_write_state": "CLOSED",
                "live_credentials_loaded": False,
                "live_execution_actions_created": False,
                "venue_live_writes_observed": False,
            }
        },
        "live_safety": {
            "real_write_state": "CLOSED",
            "current_activation_id": None,
            "live_credentials_loaded": False,
        },
        "product_build": {"current_product_build_id": None},
    }


class ConstructionPlanValidatorTests(unittest.TestCase):
    def codes(self, plan: dict[str, object]) -> set[str]:
        return {item.code for item in validate_plan(plan)}

    def test_accepts_minimal_fail_closed_current_plan(self) -> None:
        self.assertEqual(validate_plan(current_plan()), [])

    def test_runtime_projections_must_agree(self) -> None:
        plan = current_plan()
        plan["live_safety"]["real_write_state"] = "OPEN"  # type: ignore[index]

        self.assertIn("GOV-RUNTIME-004", self.codes(plan))

    def test_closed_runtime_cannot_have_loaded_credentials(self) -> None:
        plan = current_plan()
        plan["live_safety"]["live_credentials_loaded"] = True  # type: ignore[index]

        self.assertIn("GOV-RUNTIME-003", self.codes(plan))

    def test_closed_runtime_cannot_record_live_execution_actions(self) -> None:
        plan = current_plan()
        runtime = plan["current_facts"]["runtime"]  # type: ignore[index]
        runtime["live_execution_actions_created"] = True  # type: ignore[index]

        self.assertIn("GOV-RUNTIME-005", self.codes(plan))

    def test_closed_runtime_cannot_record_venue_live_writes(self) -> None:
        plan = current_plan()
        runtime = plan["current_facts"]["runtime"]  # type: ignore[index]
        runtime["venue_live_writes_observed"] = True  # type: ignore[index]

        self.assertIn("GOV-RUNTIME-006", self.codes(plan))

    def test_open_runtime_requires_build_activation_and_current_facts(self) -> None:
        plan = current_plan()
        plan["current_facts"]["runtime"]["real_write_state"] = "OPEN"  # type: ignore[index]
        plan["live_safety"]["real_write_state"] = "OPEN"  # type: ignore[index]

        codes = self.codes(plan)

        self.assertIn("GOV-RUNTIME-OPEN-001", codes)
        self.assertIn("GOV-RUNTIME-OPEN-002", codes)

    def test_accepts_open_runtime_with_direct_prerequisites(self) -> None:
        plan = current_plan()
        plan["current_facts"]["runtime"]["real_write_state"] = "OPEN"  # type: ignore[index]
        live_safety = plan["live_safety"]  # type: ignore[assignment]
        live_safety.update(  # type: ignore[union-attr]
            {
                "real_write_state": "OPEN",
                "current_activation_id": "activation-1",
                "database_current": True,
                "unique_writer_confirmed": True,
                "facts_current": True,
            }
        )
        plan["product_build"]["current_product_build_id"] = "build-1"  # type: ignore[index]

        self.assertEqual(validate_plan(plan), [])

if __name__ == "__main__":
    unittest.main()
