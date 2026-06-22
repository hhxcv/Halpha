from __future__ import annotations

import pytest

from halpha.runtime.public_http import market_proxy_url_from_market, urlopen_from_public_proxy


class PublicHTTPTestError(Exception):
    pass


def test_urlopen_from_public_proxy_builds_bounded_proxy_handler() -> None:
    proxy_handlers: list[dict[str, str]] = []

    def fake_proxy_handler(proxies: dict[str, str]) -> dict[str, str]:
        proxy_handlers.append(proxies)
        return proxies

    class FakeOpener:
        def open(self, request, timeout):
            return (request, timeout)

    def fake_opener_factory(handler):
        assert handler == {
            "http": "http://proxy.example:8080",
            "https": "http://proxy.example:8080",
        }
        return FakeOpener()

    urlopen_func = urlopen_from_public_proxy(
        " http://proxy.example:8080 ",
        error_factory=PublicHTTPTestError,
        default_urlopen=lambda request, timeout: None,
        proxy_handler_factory=fake_proxy_handler,
        opener_factory=fake_opener_factory,
    )

    assert urlopen_func("request", timeout=10) == ("request", 10)
    assert proxy_handlers == [
        {
            "http": "http://proxy.example:8080",
            "https": "http://proxy.example:8080",
        }
    ]


def test_market_proxy_url_rejects_credentials_without_echoing_secret() -> None:
    secret = "http://user:password@proxy.example:8080"

    with pytest.raises(PublicHTTPTestError) as exc_info:
        market_proxy_url_from_market(
            {
                "proxy": {
                    "enabled": True,
                    "url": secret,
                }
            },
            error_factory=PublicHTTPTestError,
            require_url_when_enabled=True,
        )

    message = str(exc_info.value)
    assert message == "market.proxy.url must not include credentials."
    assert "user" not in message
    assert "password" not in message
    assert "proxy.example" not in message
