from __future__ import annotations

from pathlib import Path
from typing import Any


DEFAULT_DASHBOARD_HOST = "127.0.0.1"
DEFAULT_DASHBOARD_PORT = 8765
LOCAL_DASHBOARD_HOSTS = {"127.0.0.1", "localhost", "::1"}


class DashboardError(Exception):
    def __init__(self, message: str, *, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def create_dashboard_app(
    config: dict[str, Any],
    *,
    config_path: Path,
    host: str = DEFAULT_DASHBOARD_HOST,
    port: int = DEFAULT_DASHBOARD_PORT,
) -> Any:
    try:
        from fastapi import FastAPI
    except ModuleNotFoundError as exc:
        raise DashboardError("FastAPI is required to run the dashboard.") from exc

    validate_dashboard_host(host)
    validate_dashboard_port(port)
    app = FastAPI(title="Halpha Dashboard", version="0.0.0")
    health = dashboard_health(config, config_path=config_path, host=host, port=port)

    @app.get("/")
    def root() -> dict[str, Any]:
        return {
            "service": "halpha_dashboard",
            "status": health["status"],
            "health": "/api/health",
        }

    @app.get("/api/health")
    def health_endpoint() -> dict[str, Any]:
        return health

    return app


def run_dashboard_service(
    config: dict[str, Any],
    *,
    config_path: Path,
    host: str = DEFAULT_DASHBOARD_HOST,
    port: int = DEFAULT_DASHBOARD_PORT,
) -> None:
    try:
        import uvicorn
    except ModuleNotFoundError as exc:
        raise DashboardError("Uvicorn is required to run the dashboard.") from exc

    app = create_dashboard_app(config, config_path=config_path, host=host, port=port)
    uvicorn.run(app, host=host, port=port)


def dashboard_health(
    config: dict[str, Any],
    *,
    config_path: Path,
    host: str = DEFAULT_DASHBOARD_HOST,
    port: int = DEFAULT_DASHBOARD_PORT,
) -> dict[str, Any]:
    validate_dashboard_host(host)
    validate_dashboard_port(port)
    return {
        "artifact_type": "dashboard_health",
        "service": "halpha_dashboard",
        "status": "ok",
        "local_only": True,
        "host": host,
        "port": port,
        "config": {
            "loaded": True,
            "ref": dashboard_config_ref(config_path),
        },
        "features": {
            "overview_api": "not_implemented",
            "artifact_preview_api": "not_implemented",
            "job_runner": "not_implemented",
            "frontend_ui": "not_implemented",
        },
    }


def validate_dashboard_host(host: str) -> None:
    if host not in LOCAL_DASHBOARD_HOSTS:
        supported = ", ".join(sorted(LOCAL_DASHBOARD_HOSTS))
        raise DashboardError(f"dashboard host must be local-only. Supported hosts: {supported}.")


def validate_dashboard_port(port: int) -> None:
    if port < 1 or port > 65535:
        raise DashboardError("dashboard port must be between 1 and 65535.")


def dashboard_config_ref(config_path: Path) -> str:
    path = Path(config_path)
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return "<external-config>"


def sanitize_dashboard_message(message: str, *, config_path: Path) -> str:
    safe_ref = dashboard_config_ref(config_path)
    variants = {str(config_path), config_path.as_posix()}
    try:
        variants.add(str(config_path.resolve()))
        variants.add(config_path.resolve().as_posix())
    except OSError:
        pass

    sanitized = message
    for value in sorted(variants, key=len, reverse=True):
        if value:
            sanitized = sanitized.replace(value, safe_ref)
    return sanitized
