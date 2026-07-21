from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime

from halpha.app import planning_api as planning_api_module
from halpha.app.planning_api import PostgreSQLPlanningApi


NOW = datetime(2026, 7, 20, 1, tzinfo=UTC)


def test_receipt_poll_finalizes_completed_activation(monkeypatch) -> None:
    rows = [
        (
            "receipt-1",
            "command-1",
            "TRADEPLAN",
            "PROCESSING",
            2,
            "EXIT_RESPONSIBILITY_ACCEPTED",
            {"activation_id": "activation-1"},
            ["EXIT_CLOSURE_DIGEST"],
            "a" * 64,
            NOW,
            NOW,
            "activation-1",
        ),
        (
            "receipt-1",
            "command-1",
            "TRADEPLAN",
            "EFFECTIVE",
            3,
            "EXIT_COMPLETED",
            {"activation_id": "activation-1", "result_ref": "review-1"},
            [],
            "b" * 64,
            NOW,
            NOW,
            "activation-1",
        ),
    ]
    finalized: list[str] = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        @staticmethod
        def transaction():
            return nullcontext()

        @staticmethod
        def execute(_query, _parameters):
            row = rows.pop(0)
            return type("Cursor", (), {"fetchone": staticmethod(lambda: row)})()

    class ControlService:
        def __init__(self, _connection, _environment_id):
            pass

        @staticmethod
        def finalize_completed_activation(activation_id: str, **_kwargs):
            finalized.append(activation_id)

    monkeypatch.setattr(
        planning_api_module,
        "ActivationControlService",
        ControlService,
    )
    api = object.__new__(PostgreSQLPlanningApi)
    api._environment_id = "demo-main"
    api._connect = Connection

    receipt = api.receipt("receipt-1")

    assert finalized == ["activation-1"]
    assert receipt["state"] == "EFFECTIVE"
    assert receipt["reason_code"] == "EXIT_COMPLETED"
    assert receipt["pending_responsibility_refs"] == []
