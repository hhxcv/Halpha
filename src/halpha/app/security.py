"""Local-request web security primitives for the App process."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol
from urllib.parse import urlsplit

from asgi_csrf import asgi_csrf
from pydantic import SecretStr
from starlette.responses import JSONResponse


class ASGIApp(Protocol):
    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None: ...


class CsrfMiddleware:
    """Thin Starlette middleware adapter around the selected ASGI component."""

    def __init__(self, app: ASGIApp, *, signing_secret: SecretStr) -> None:
        self._app = asgi_csrf(
            app,
            cookie_name="halpha_csrf",
            http_header="x-csrftoken",
            signing_secret=signing_secret.get_secret_value(),
            always_protect=[],
            always_set_cookie=True,
            skip_if_scope=None,
            cookie_path="/",
            cookie_domain=None,
            cookie_secure=False,
            cookie_samesite="Strict",
        )

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        await self._app(scope, receive, send)


class LocalRequestBoundaryMiddleware:
    """Reject non-local origins and Authorization-based identity before CSRF."""

    _SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}

    def __init__(self, app: ASGIApp, *, port: int) -> None:
        self._app = app
        self._port = port

    def _allowed_origin(self, value: str) -> bool:
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError:
            return False
        return (
            parsed.scheme == "http"
            and parsed.hostname in {"127.0.0.1", "localhost"}
            and port == self._port
            and not parsed.username
            and not parsed.password
        )

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        if "authorization" in headers:
            response = JSONResponse(
                {"detail": {"code": "AUTHORIZATION_HEADER_FORBIDDEN"}},
                status_code=400,
            )
            await response(scope, receive, send)
            return

        if scope.get("method") not in self._SAFE_METHODS:
            origin = headers.get("origin")
            referer = headers.get("referer")
            if not (
                (origin is not None and self._allowed_origin(origin))
                or (origin is None and referer is not None and self._allowed_origin(referer))
            ):
                response = JSONResponse(
                    {"detail": {"code": "LOCAL_ORIGIN_REQUIRED"}},
                    status_code=403,
                )
                await response(scope, receive, send)
                return

        async def send_with_headers(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                response_headers = list(message.get("headers", []))
                response_headers.extend(
                    [
                        (b"cache-control", b"no-store"),
                        (b"content-security-policy", b"default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"),
                        (b"referrer-policy", b"same-origin"),
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                    ]
                )
                message = {**message, "headers": response_headers}
            await send(message)

        await self._app(scope, receive, send_with_headers)
