from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlparse

from halpha.runtime.public_rate_limits import (
    is_public_api_rate_limit_response,
    raise_if_public_api_rate_limited,
    record_public_api_rate_limit,
    retry_after_seconds_from_headers,
)


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
    rate_limit_config_path: Path | None = None,
    rate_limit_source: str | None = None,
) -> UrlopenCallable:
    normalized = normalize_public_proxy_url(
        proxy_url,
        error_factory=error_factory,
        missing_url_message=missing_url_message,
        invalid_url_message=invalid_url_message,
        credentials_message=credentials_message,
    )
    if normalized is None:
        return _rate_limited_urlopen(
            default_urlopen,
            rate_limit_config_path=rate_limit_config_path,
            rate_limit_source=rate_limit_source,
        )
    opener = opener_factory(proxy_handler_factory({"http": normalized, "https": normalized}))
    return _rate_limited_urlopen(
        opener.open,
        rate_limit_config_path=rate_limit_config_path,
        rate_limit_source=rate_limit_source,
    )


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


def _rate_limited_urlopen(
    urlopen_func: UrlopenCallable,
    *,
    rate_limit_config_path: Path | None,
    rate_limit_source: str | None,
) -> UrlopenCallable:
    if rate_limit_config_path is None:
        return urlopen_func

    def wrapped(request: Any, *args: Any, **kwargs: Any) -> Any:
        url = _request_url(request)
        raise_if_public_api_rate_limited(
            config_path=rate_limit_config_path,
            url=url,
            source=rate_limit_source,
        )
        try:
            return urlopen_func(request, *args, **kwargs)
        except HTTPError as exc:
            headers = getattr(exc, "headers", None)
            if is_public_api_rate_limit_response(exc.code, headers=headers):
                record_public_api_rate_limit(
                    config_path=rate_limit_config_path,
                    url=url,
                    source=rate_limit_source,
                    status_code=exc.code,
                    retry_after_seconds=retry_after_seconds_from_headers(headers),
                )
            raise

    return wrapped


def _request_url(request: Any) -> str:
    value = getattr(request, "full_url", None)
    if isinstance(value, str) and value:
        return value
    value = getattr(request, "get_full_url", None)
    if callable(value):
        try:
            full_url = value()
        except Exception:
            full_url = None
        if isinstance(full_url, str) and full_url:
            return full_url
    return str(request)
