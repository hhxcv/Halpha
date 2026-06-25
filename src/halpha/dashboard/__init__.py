from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORT_MODULES = {
    "DEFAULT_DASHBOARD_DISPLAY_TIMEZONE": "halpha.dashboard.constants",
    "DEFAULT_DASHBOARD_HOST": "halpha.dashboard.app",
    "DEFAULT_DASHBOARD_PORT": "halpha.dashboard.app",
    "DashboardError": "halpha.dashboard.app",
    "create_dashboard_app": "halpha.dashboard.app",
    "dashboard_config_ref": "halpha.dashboard.settings",
    "dashboard_display_timezone": "halpha.dashboard.app",
    "dashboard_health": "halpha.dashboard.app",
    "dashboard_service_status": "halpha.dashboard.app",
    "load_dashboard_startup_config": "halpha.dashboard.app",
    "restart_dashboard_service": "halpha.dashboard.app",
    "run_dashboard_service": "halpha.dashboard.app",
    "start_dashboard_service": "halpha.dashboard.app",
    "stop_dashboard_service": "halpha.dashboard.app",
    "sanitize_dashboard_message": "halpha.dashboard.settings",
    "validate_dashboard_host": "halpha.dashboard.app",
    "validate_dashboard_port": "halpha.dashboard.app",
}

__all__ = list(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value
