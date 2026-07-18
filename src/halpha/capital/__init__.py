"""CAP authority, allocation, Decimal checking, and loss ownership."""

from halpha.capital.checks import (
    allocate_plan,
    check_action,
    compute_activation_loss,
    effective_leverage,
    latch_max_loss,
)

__all__ = [
    "allocate_plan",
    "check_action",
    "compute_activation_loss",
    "effective_leverage",
    "latch_max_loss",
]
