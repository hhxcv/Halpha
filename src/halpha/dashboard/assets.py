from __future__ import annotations

from functools import lru_cache
from importlib.resources import files


DASHBOARD_ASSET_MEDIA_TYPES = {
    "index.html": "text/html; charset=utf-8",
    "dashboard.css": "text/css; charset=utf-8",
    "dashboard.js": "application/javascript; charset=utf-8",
}


@lru_cache(maxsize=len(DASHBOARD_ASSET_MEDIA_TYPES))
def dashboard_asset_text(name: str) -> str:
    if name not in DASHBOARD_ASSET_MEDIA_TYPES:
        raise KeyError(name)
    return files("halpha.dashboard.static").joinpath(name).read_text(encoding="utf-8")


def dashboard_asset_media_type(name: str) -> str | None:
    return DASHBOARD_ASSET_MEDIA_TYPES.get(name)
