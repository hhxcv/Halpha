from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from halpha.planning.adapter import (
    ActivationAdapterLifecycle,
    ActivationAdapterSpec,
    HalphaStrategyAdapter,
    strategy_id_for_activation,
)
from halpha.planning.registry import OneShotParameters
from halpha.planning.strategies.one_shot import (
    ActivationStrategyState,
    OneShotDonchianAtrLogic,
)


@dataclass
class FakeController:
    created: list[object] = field(default_factory=list)
    stopped: list[object] = field(default_factory=list)
    removed: list[object] = field(default_factory=list)

    def create_strategy(self, strategy: object, start: bool = True) -> None:
        assert start is True
        self.created.append(strategy)

    def stop_strategy(self, strategy: object) -> None:
        self.stopped.append(strategy)

    def remove_strategy(self, strategy: object) -> None:
        self.removed.append(strategy)


def make_adapter(activation_id: str) -> HalphaStrategyAdapter:
    return HalphaStrategyAdapter(
        activation_id=activation_id,
        logic=OneShotDonchianAtrLogic(OneShotParameters(direction="LONG")),
        state_provider=ActivationStrategyState,
        proposal_sink=lambda _proposal: None,
    )


def test_strategy_id_is_stable_per_activation_and_distinct_across_activations() -> None:
    assert strategy_id_for_activation("activation-a") == strategy_id_for_activation("activation-a")
    assert strategy_id_for_activation("activation-a") != strategy_id_for_activation("activation-b")


def test_lifecycle_creates_one_adapter_and_stops_before_remove() -> None:
    controller = FakeController()
    lifecycle = ActivationAdapterLifecycle(controller)
    spec = ActivationAdapterSpec(
        activation_id="activation-a",
        factory=lambda: make_adapter("activation-a"),
    )
    first = lifecycle.start(spec)
    replay = lifecycle.start(spec)
    assert replay is first
    assert controller.created == [first]
    assert lifecycle.activation_ids == ("activation-a",)

    lifecycle.stop_and_remove("activation-a")
    assert controller.stopped == [first]
    assert controller.removed == [first]
    assert lifecycle.activation_ids == ()


def test_lifecycle_rejects_factory_activation_mismatch() -> None:
    lifecycle = ActivationAdapterLifecycle(FakeController())
    with pytest.raises(ValueError, match="ADAPTER_ACTIVATION_MISMATCH"):
        lifecycle.start(
            ActivationAdapterSpec(
                activation_id="activation-a",
                factory=lambda: make_adapter("activation-b"),
            )
        )
