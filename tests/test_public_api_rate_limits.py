from __future__ import annotations

from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from halpha.runtime.public_http import urlopen_from_public_proxy
from halpha.runtime.public_rate_limits import (
    PublicApiRateLimitError,
    active_public_api_cooldown,
    is_public_api_rate_limit_response,
    read_public_api_rate_limit_state,
    record_public_api_rate_limit,
    retry_after_seconds_from_headers,
    sanitize_public_api_error_message,
)


class PublicHTTPTestError(Exception):
    pass


def test_public_api_rate_limit_state_persists_cooldown_in_runtime_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.yaml"
    config_path.write_text("run:\n  output_dir: runs\n", encoding="utf-8")

    record = record_public_api_rate_limit(
        config_path=config_path,
        url="https://fapi.binance.com/futures/data/basis?symbol=BTCUSDT",
        source="binance_usdm",
        status_code=418,
        message="Way too many requests; IP banned until 1782979260000. 192.0.2.1",
        now="2026-07-02T08:00:00Z",
    )

    assert record["host"] == "fapi.binance.com"
    assert record["source"] == "binance_usdm"
    assert record["status_code"] == 418
    assert record["cooldown_until"] == "2026-07-02T08:01:00Z"
    assert "<redacted-ip>" in record["reason"]

    restarted_state = read_public_api_rate_limit_state(config_path=config_path)
    assert restarted_state["cooldowns"]["fapi.binance.com"]["cooldown_until"] == "2026-07-02T08:01:00Z"

    active = active_public_api_cooldown(
        config_path=config_path,
        url="https://fapi.binance.com/fapi/v1/openInterest",
        source="binance_usdm",
        now="2026-07-02T08:00:30Z",
    )
    assert active is not None
    assert active["retry_after_seconds"] == 30


def test_public_api_rate_limit_state_ignores_expired_cooldown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.yaml"
    config_path.write_text("run:\n  output_dir: runs\n", encoding="utf-8")
    record_public_api_rate_limit(
        config_path=config_path,
        url="https://api.example.com/resource",
        source="example",
        status_code=429,
        retry_after_seconds=60,
        now="2026-07-02T08:00:00Z",
    )

    assert (
        active_public_api_cooldown(
            config_path=config_path,
            url="https://api.example.com/other",
            source="example",
            now="2026-07-02T08:02:00Z",
        )
        is None
    )


def test_urlopen_from_public_proxy_records_retry_after_and_blocks_next_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.yaml"
    config_path.write_text("run:\n  output_dir: runs\n", encoding="utf-8")
    calls: list[str] = []

    def fake_urlopen(request: Request, timeout: int):
        calls.append(request.full_url)
        raise HTTPError(request.full_url, 429, "Too Many Requests", {"Retry-After": "120"}, None)

    urlopen_func = urlopen_from_public_proxy(
        None,
        error_factory=PublicHTTPTestError,
        default_urlopen=fake_urlopen,
        proxy_handler_factory=lambda proxies: proxies,
        opener_factory=lambda handler: None,
        rate_limit_config_path=config_path,
        rate_limit_source="example",
    )

    request = Request("https://api.example.com/data")
    with pytest.raises(HTTPError):
        urlopen_func(request, timeout=20)
    with pytest.raises(PublicApiRateLimitError):
        urlopen_func(request, timeout=20)

    assert calls == ["https://api.example.com/data"]
    active = active_public_api_cooldown(
        config_path=config_path,
        url="https://api.example.com/other",
        source="example",
    )
    assert active is not None
    assert active["status_code"] == 429
    assert active["retry_after_seconds"] > 0


def test_urlopen_from_public_proxy_records_non_429_retry_after(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.yaml"
    config_path.write_text("run:\n  output_dir: runs\n", encoding="utf-8")

    def fake_urlopen(request: Request, timeout: int):
        raise HTTPError(request.full_url, 503, "Service Unavailable", {"Retry-After": "45"}, None)

    urlopen_func = urlopen_from_public_proxy(
        None,
        error_factory=PublicHTTPTestError,
        default_urlopen=fake_urlopen,
        proxy_handler_factory=lambda proxies: proxies,
        opener_factory=lambda handler: None,
        rate_limit_config_path=config_path,
        rate_limit_source="example",
    )

    with pytest.raises(HTTPError):
        urlopen_func(Request("https://api.example.com/data"), timeout=20)

    active = active_public_api_cooldown(
        config_path=config_path,
        url="https://api.example.com/other",
        source="example",
    )
    assert active is not None
    assert active["status_code"] == 503
    assert active["retry_after_seconds"] > 0


def test_rate_limit_response_detects_body_text_without_429() -> None:
    assert is_public_api_rate_limit_response(403, message="quota exceeded for public API key")
    assert is_public_api_rate_limit_response(503, headers={"Retry-After": "30"})
    assert not is_public_api_rate_limit_response(503, message="upstream temporarily unavailable")


def test_retry_after_supports_http_date() -> None:
    retry_after = retry_after_seconds_from_headers(
        {"Retry-After": "Thu, 02 Jul 2026 08:05:00 GMT"},
        now="2026-07-02T08:04:30Z",
    )

    assert retry_after == 30


def test_public_api_error_message_sanitizes_private_values() -> None:
    message = "proxy http://127.0.0.1:7890 failed for http://localhost/private from 10.0.0.1"

    sanitized = sanitize_public_api_error_message(message)

    assert sanitized == "proxy <redacted-url> failed for <redacted-url> from <redacted-ip>"
