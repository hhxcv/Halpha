from types import SimpleNamespace

from halpha.capital.models import StopCategory
from halpha.capital.service import CapitalApplicationService


def _service(*categories: StopCategory) -> CapitalApplicationService:
    service = object.__new__(CapitalApplicationService)
    service._planning = SimpleNamespace(
        get_activation=lambda _activation_id: SimpleNamespace(
            activation_id="activation-1",
            account_ref="account-1",
        )
    )
    service._capital = SimpleNamespace(
        lock_current_stop_states=lambda **_values: (
            SimpleNamespace(stopped_categories=frozenset(categories)),
        )
    )
    return service


def test_new_risk_state_is_visible_before_strategy_proposal() -> None:
    assert _service().new_risk_allowed("activation-1") is True
    assert (
        _service(StopCategory.NEW_RISK).new_risk_allowed("activation-1")
        is False
    )
    assert (
        _service(StopCategory.ALL_EXCHANGE_CHANGES).new_risk_allowed(
            "activation-1"
        )
        is False
    )
