from decimal import Decimal

import pytest

from halpha.domain_values import (
    DomainValidationError,
    canonical_decimal,
    decimal_from_string,
)


@pytest.mark.parametrize(
    "value",
    (
        "1e1000000",
        "1e-1000000",
        "1" * 129,
        "1." + ("0" * 256),
    ),
)
def test_decimal_from_string_rejects_resource_exhausting_values(value: str) -> None:
    with pytest.raises(DomainValidationError, match="VALUE_INVALID"):
        decimal_from_string(value, code="VALUE_INVALID")


@pytest.mark.parametrize(
    "value",
    (
        Decimal("1e1000000"),
        Decimal("1e-1000000"),
        Decimal("0e-1000000"),
    ),
)
def test_canonical_decimal_rejects_resource_exhausting_values(
    value: Decimal,
) -> None:
    with pytest.raises(DomainValidationError, match="DECIMAL_OUT_OF_RANGE"):
        canonical_decimal(value)


def test_decimal_resource_bound_keeps_normal_high_precision_values() -> None:
    value = "1.492537313432835820895522388"

    assert decimal_from_string(value, code="VALUE_INVALID") == Decimal(value)
    assert canonical_decimal(Decimal(value)) == value
