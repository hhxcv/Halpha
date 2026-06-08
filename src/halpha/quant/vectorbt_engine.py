from __future__ import annotations

import os
import tempfile
from functools import lru_cache
from importlib import metadata
from pathlib import Path
from typing import Any


ENGINE_NAME = "vectorbt"


def engine_metadata() -> dict[str, str]:
    try:
        version = metadata.version(ENGINE_NAME)
    except metadata.PackageNotFoundError:
        version = "unknown"
    return {
        "name": ENGINE_NAME,
        "version": version,
    }


@lru_cache(maxsize=1)
def load_vectorbt() -> Any:
    _prepare_numba_cache()
    import vectorbt as vbt

    return vbt


def _prepare_numba_cache() -> None:
    if os.environ.get("NUMBA_CACHE_DIR"):
        return
    cache_dir = Path(tempfile.gettempdir()) / "halpha-numba-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["NUMBA_CACHE_DIR"] = str(cache_dir)
