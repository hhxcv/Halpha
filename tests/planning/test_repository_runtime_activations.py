from __future__ import annotations

from types import SimpleNamespace

from halpha.planning.repository import PostgreSQLPlanningRepository


class _Rows:
    @staticmethod
    def fetchall() -> list[tuple[str]]:
        return [("running-1",), ("takeover-1",)]


class _Connection:
    def __init__(self) -> None:
        self.statement = ""
        self.parameters: tuple[str, ...] = ()

    def execute(self, statement: str, parameters: tuple[str, ...]) -> _Rows:
        self.statement = statement
        self.parameters = parameters
        return _Rows()


def test_runtime_responsibility_inventory_keeps_user_takeover_until_completion() -> None:
    connection = _Connection()
    repository = object.__new__(PostgreSQLPlanningRepository)
    repository._connection = connection
    repository._environment_id = "demo"
    repository.get_activation = lambda activation_id: SimpleNamespace(
        activation_id=activation_id
    )

    activations = repository.list_runtime_responsibility_activations()

    assert tuple(item.activation_id for item in activations) == (
        "running-1",
        "takeover-1",
    )
    assert "lifecycle <> 'COMPLETED'" in connection.statement
    assert "USER_TAKEOVER" not in connection.statement
    assert connection.parameters == ("demo",)
