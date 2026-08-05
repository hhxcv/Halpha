from types import SimpleNamespace
from typing import cast

from fastapi import FastAPI

from halpha.app.__main__ import _uvicorn_config
from halpha.configuration import AppSettingsView


def test_uvicorn_config_bounds_graceful_shutdown() -> None:
    role_settings = cast(
        AppSettingsView,
        SimpleNamespace(
            app=SimpleNamespace(
                bind="127.0.0.1",
                port=8765,
                workers=1,
                reload=False,
            )
        ),
    )

    config = _uvicorn_config(FastAPI(), role_settings)

    assert config.timeout_graceful_shutdown == 10
    assert config.proxy_headers is False
    assert config.server_header is False
