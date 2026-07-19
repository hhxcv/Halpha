from __future__ import annotations

import unittest

from governance.validate_current_plan import validate_plan


def current_plan() -> dict[str, object]:
    return {
        "document_id": "HALPHA-PLAN-001",
        "level": "L4",
        "language": "zh-CN",
        "product_build": {"current_product_build_id": None},
        "real_account_trading": {
            "exchange_change_requests_allowed": False,
            "credentials_loaded": False,
            "current_activation_id": None,
            "execution_actions_created": False,
            "exchange_changes_observed": False,
            "database_current": False,
            "unique_executor_confirmed": False,
            "facts_current": False,
        },
    }


class CurrentPlanValidatorTests(unittest.TestCase):
    def codes(self, plan: dict[str, object]) -> set[str]:
        return {item.code for item in validate_plan(plan)}

    def test_accepts_disabled_real_account_trading(self) -> None:
        self.assertEqual(validate_plan(current_plan()), [])

    def test_requires_an_explicit_exchange_request_flag(self) -> None:
        plan = current_plan()
        del plan["real_account_trading"]["exchange_change_requests_allowed"]  # type: ignore[index]

        self.assertIn("GOV-REAL-001", self.codes(plan))

    def test_disabled_state_cannot_have_loaded_credentials(self) -> None:
        plan = current_plan()
        plan["real_account_trading"]["credentials_loaded"] = True  # type: ignore[index]

        self.assertIn("GOV-REAL-002", self.codes(plan))

    def test_disabled_state_cannot_record_execution_actions(self) -> None:
        plan = current_plan()
        plan["real_account_trading"]["execution_actions_created"] = True  # type: ignore[index]

        self.assertIn("GOV-REAL-002", self.codes(plan))

    def test_disabled_state_cannot_record_exchange_changes(self) -> None:
        plan = current_plan()
        plan["real_account_trading"]["exchange_changes_observed"] = True  # type: ignore[index]

        self.assertIn("GOV-REAL-002", self.codes(plan))

    def test_allowed_requests_require_current_identities_and_facts(self) -> None:
        plan = current_plan()
        plan["real_account_trading"]["exchange_change_requests_allowed"] = True  # type: ignore[index]

        codes = self.codes(plan)

        self.assertIn("GOV-REAL-003", codes)
        self.assertIn("GOV-REAL-004", codes)

    def test_accepts_allowed_requests_with_direct_prerequisites(self) -> None:
        plan = current_plan()
        facts = plan["real_account_trading"]  # type: ignore[assignment]
        facts.update(  # type: ignore[union-attr]
            {
                "exchange_change_requests_allowed": True,
                "credentials_loaded": True,
                "current_activation_id": "activation-1",
                "database_current": True,
                "unique_executor_confirmed": True,
                "facts_current": True,
            }
        )
        plan["product_build"]["current_product_build_id"] = "build-1"  # type: ignore[index]

        self.assertEqual(validate_plan(plan), [])


if __name__ == "__main__":
    unittest.main()
