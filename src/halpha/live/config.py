from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from halpha.live.contracts import DEFAULT_LIVE_TICK_SECONDS, LIVE_DATA_TYPES


@dataclass(frozen=True)
class LiveCollectionConfig:
    data_type: str
    enabled: bool
    cadence_seconds: int | None
    lookback_seconds: int | None
    lookahead_seconds: int | None


@dataclass(frozen=True)
class LiveSettings:
    enabled: bool
    tick_seconds: int
    collections: dict[str, LiveCollectionConfig]


def load_live_settings(config: dict[str, Any]) -> LiveSettings:
    live = config.get("live") if isinstance(config.get("live"), dict) else {}
    collections_config = live.get("collections") if isinstance(live.get("collections"), dict) else {}
    collections: dict[str, LiveCollectionConfig] = {}
    for data_type in LIVE_DATA_TYPES:
        item = collections_config.get(data_type) if isinstance(collections_config.get(data_type), dict) else {}
        collections[data_type] = LiveCollectionConfig(
            data_type=data_type,
            enabled=item.get("enabled") is True,
            cadence_seconds=_optional_positive_int(item.get("cadence_seconds")),
            lookback_seconds=_optional_positive_int(item.get("lookback_seconds")),
            lookahead_seconds=_optional_positive_int(item.get("lookahead_seconds")),
        )
    return LiveSettings(
        enabled=live.get("enabled") is True,
        tick_seconds=_optional_positive_int(live.get("tick_seconds")) or DEFAULT_LIVE_TICK_SECONDS,
        collections=collections,
    )


def _optional_positive_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None
