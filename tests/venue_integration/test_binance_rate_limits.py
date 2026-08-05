from types import SimpleNamespace

import pytest

import halpha.venue_integration.binance_rate_limits as rate_limit_module
from halpha.venue_integration.binance_rate_limits import (
    MAX_BINANCE_RATE_LIMIT_BACKOFF_SECONDS,
    binance_retry_after_seconds,
)


def test_binance_retry_after_uses_server_header() -> None:
    error = SimpleNamespace(status=429, headers={"Retry-After": "135"})

    assert binance_retry_after_seconds(error) == 135.0


def test_binance_ip_ban_uses_safe_fallback_without_header() -> None:
    error = SimpleNamespace(status=418, headers={})

    assert binance_retry_after_seconds(error) == 120.0


@pytest.mark.parametrize(
    "message",
    (
        {"code": -1003, "msg": "Way too many requests; IP banned until 2000000090000."},
        '{"code":-1003,"msg":"Way too many requests; IP banned until 2000000090000."}',
    ),
)
def test_binance_ip_ban_uses_documented_body_timestamp_without_header(
    monkeypatch: pytest.MonkeyPatch,
    message: object,
) -> None:
    monkeypatch.setattr(rate_limit_module, "time", lambda: 2_000_000_000.0)
    error = SimpleNamespace(status=418, headers={}, message=message)

    assert binance_retry_after_seconds(error) == 91.0


def test_binance_ip_ban_body_timestamp_is_bounded_to_documented_maximum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rate_limit_module, "time", lambda: 2_000_000_000.0)
    error = SimpleNamespace(
        status=418,
        headers={},
        message={
            "code": -1003,
            "msg": "Way too many requests; IP banned until 2000345600000.",
        },
    )

    assert (
        binance_retry_after_seconds(error)
        == MAX_BINANCE_RATE_LIMIT_BACKOFF_SECONDS
    )


def test_non_rate_limit_error_has_no_cooldown() -> None:
    error = SimpleNamespace(status=503, headers={"Retry-After": "30"})

    assert binance_retry_after_seconds(error) is None
