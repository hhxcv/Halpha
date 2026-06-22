from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse


ErrorFactory = Callable[[str], Exception]
UrlopenCallable = Callable[..., Any]


def market_proxy_url_from_config(
    config: dict[str, Any],
    *,
    error_factory: ErrorFactory,
    require_url_when_enabled: bool = False,
    missing_url_message: str = "market.proxy.url must be a non-empty string.",
    invalid_url_message: str = "market.proxy.url must be an http or https URL.",
    credentials_message: str = "market.proxy.url must not include credentials.",
) -> str | None:
    market = config.get("market")
    if not isinstance(market, dict):
        return None
    return market_proxy_url_from_market(
        market,
        error_factory=error_factory,
        require_url_when_enabled=require_url_when_enabled,
        missing_url_message=missing_url_message,
        invalid_url_message=invalid_url_message,
        credentials_message=credentials_message,
    )


def market_proxy_url_from_market(
    market: dict[str, Any],
    *,
    error_factory: ErrorFactory,
    require_url_when_enabled: bool = False,
    missing_url_message: str = "market.proxy.url must be a non-empty string.",
    invalid_url_message: str = "market.proxy.url must be an http or https URL.",
    credentials_message: str = "market.proxy.url must not include credentials.",
) -> str | None:
    proxy = market.get("proxy")
    if not isinstance(proxy, dict) or proxy.get("enabled") is not True:
        return None
    value = proxy.get("url")
    if not isinstance(value, str) or not value.strip():
        if require_url_when_enabled:
            raise error_factory(missing_url_message)
        return None
    return normalize_public_proxy_url(
        value,
        error_factory=error_factory,
        missing_url_message=missing_url_message,
        invalid_url_message=invalid_url_message,
        credentials_message=credentials_message,
    )


def urlopen_from_public_proxy(
    proxy_url: str | None,
    *,
    error_factory: ErrorFactory,
    default_urlopen: UrlopenCallable,
    proxy_handler_factory: Callable[[dict[str, str]], Any],
    opener_factory: Callable[[Any], Any],
    missing_url_message: str = "market.proxy.url must be a non-empty string.",
    invalid_url_message: str = "market.proxy.url must be an http or https URL.",
    credentials_message: str = "market.proxy.url must not include credentials.",
) -> UrlopenCallable:
    normalized = normalize_public_proxy_url(
        proxy_url,
        error_factory=error_factory,
        missing_url_message=missing_url_message,
        invalid_url_message=invalid_url_message,
        credentials_message=credentials_message,
    )
    if normalized is None:
        return default_urlopen
    opener = opener_factory(proxy_handler_factory({"http": normalized, "https": normalized}))
    return opener.open


def normalize_public_proxy_url(
    value: Any,
    *,
    error_factory: ErrorFactory,
    missing_url_message: str = "market.proxy.url must be a non-empty string.",
    invalid_url_message: str = "market.proxy.url must be an http or https URL.",
    credentials_message: str = "market.proxy.url must not include credentials.",
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise error_factory(missing_url_message)
    proxy_url = value.strip()
    parsed = urlparse(proxy_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise error_factory(invalid_url_message)
    if parsed.username or parsed.password:
        raise error_factory(credentials_message)
    return proxy_url
