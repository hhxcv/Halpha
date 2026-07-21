from __future__ import annotations

import pytest

from halpha.app.projection import _executor_status_from_application_names
from halpha.product_build import (
    EXECUTOR_STARTING_APPLICATION_NAME,
    executor_ready_application_name,
)


PRODUCT_BUILD_ID = "a" * 64


@pytest.mark.parametrize(
    ("names", "expected"),
    (
        ((executor_ready_application_name(PRODUCT_BUILD_ID),), ("READY", True)),
        ((EXECUTOR_STARTING_APPLICATION_NAME,), ("STARTING", None)),
        ((executor_ready_application_name("b" * 64),), ("BUILD_MISMATCH", False)),
        ((), ("UNAVAILABLE", None)),
        (
            (
                EXECUTOR_STARTING_APPLICATION_NAME,
                executor_ready_application_name(PRODUCT_BUILD_ID),
            ),
            ("AMBIGUOUS", None),
        ),
    ),
)
def test_executor_status_is_fail_closed_for_every_non_unique_ready_session(
    names: tuple[str, ...],
    expected: tuple[str, bool | None],
) -> None:
    assert _executor_status_from_application_names(
        names,
        product_build_id=PRODUCT_BUILD_ID,
    ) == expected
