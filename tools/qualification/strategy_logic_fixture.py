from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from decimal import Decimal
from decimal import InvalidOperation


@dataclass(frozen=True)
class QualificationProposal:
    """Immutable DIRECT-only proposal value; never a venue command or product record."""

    strategy_id: str
    activation_id: str
    trigger_id: str
    instrument_id: str
    direction: str
    action: str
    risk_direction: str
    reference_price: str
    reference_source: str

    def canonical(self) -> dict[str, str]:
        return asdict(self)


class OneShotQualificationLogic:
    """Pure one-shot decision fixture shared by live and backtest qualification adapters."""

    def __init__(self, *, activation_id: str, instrument_id: str) -> None:
        self._activation_id = activation_id
        self._instrument_id = instrument_id
        self._entry_consumed = False

    def evaluate_entry(
        self,
        *,
        trigger_id: str,
        reference_price: str,
        reference_source: str,
    ) -> QualificationProposal | None:
        if self._entry_consumed:
            return None
        try:
            price = Decimal(reference_price)
        except InvalidOperation:
            return None
        if not price.is_finite() or price <= 0:
            return None

        self._entry_consumed = True
        return QualificationProposal(
            strategy_id="DIRECT_ONE_SHOT_FIXTURE_V1",
            activation_id=self._activation_id,
            trigger_id=trigger_id,
            instrument_id=self._instrument_id,
            direction="LONG",
            action="ENTRY_MARKET",
            risk_direction="INCREASE",
            reference_price=str(price),
            reference_source=reference_source,
        )
