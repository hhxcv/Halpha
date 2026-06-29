from __future__ import annotations

from typing import Any


TARGETED_PARAMS_KEY = "targeted_params"
RESOLVED_PARAMETER_PROFILE_KEY = "parameter_profile"


def resolve_strategy_for_target(
    strategy: dict[str, Any],
    *,
    source: str | None,
    symbol: str | None,
    timeframe: str | None,
) -> dict[str, Any]:
    """Return a strategy copy with target-specific params applied when configured."""

    base_params = _dict_value(strategy.get("params"))
    profile = _matching_targeted_params(
        strategy,
        source=source,
        symbol=symbol,
        timeframe=timeframe,
    )
    if profile is None:
        return {
            **strategy,
            "params": base_params,
            RESOLVED_PARAMETER_PROFILE_KEY: {
                "source": "base_params",
                "matched": False,
                "target": _target_record(source=source, symbol=symbol, timeframe=timeframe),
                "base_params": base_params,
                "override_params": {},
                "effective_params": base_params,
            },
        }

    override_params = _dict_value(profile.get("params"))
    effective_params = {**base_params, **override_params}
    return {
        **strategy,
        "params": effective_params,
        RESOLVED_PARAMETER_PROFILE_KEY: {
            "source": TARGETED_PARAMS_KEY,
            "matched": True,
            "target": _target_record(source=source, symbol=symbol, timeframe=timeframe),
            "profile": {
                "source": str(profile.get("source")),
                "symbol": str(profile.get("symbol")),
                "timeframe": str(profile.get("timeframe")),
            },
            "base_params": base_params,
            "override_params": override_params,
            "effective_params": effective_params,
        },
    }


def configured_targeted_parameter_profiles(strategy: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = strategy.get(TARGETED_PARAMS_KEY)
    if not isinstance(profiles, list):
        return []
    records = []
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        params = _dict_value(profile.get("params"))
        records.append(
            {
                "source": profile.get("source"),
                "symbol": profile.get("symbol"),
                "timeframe": profile.get("timeframe"),
                "params": params,
            }
        )
    return records


def has_targeted_parameter_profiles(strategy: dict[str, Any]) -> bool:
    return bool(configured_targeted_parameter_profiles(strategy))


def has_matching_targeted_parameter_profile(
    strategy: dict[str, Any],
    *,
    source: str | None,
    symbol: str | None,
    timeframe: str | None,
) -> bool:
    return _matching_targeted_params(
        strategy,
        source=source,
        symbol=symbol,
        timeframe=timeframe,
    ) is not None


def configured_targeted_parameter_targets(strategies: list[dict[str, Any]]) -> list[dict[str, str]]:
    records = []
    seen: set[tuple[str, str, str]] = set()
    for strategy in strategies:
        if not isinstance(strategy, dict) or strategy.get("enabled", True) is False:
            continue
        for profile in configured_targeted_parameter_profiles(strategy):
            source = str(profile.get("source") or "")
            symbol = str(profile.get("symbol") or "")
            timeframe = str(profile.get("timeframe") or "")
            if not source or not symbol or not timeframe:
                continue
            identity = (source, symbol, timeframe)
            if identity in seen:
                continue
            seen.add(identity)
            records.append({"source": source, "symbol": symbol, "timeframe": timeframe})
    return records


def parameter_profile_record(strategy: dict[str, Any]) -> dict[str, Any]:
    profile = strategy.get(RESOLVED_PARAMETER_PROFILE_KEY)
    if isinstance(profile, dict):
        return dict(profile)
    params = _dict_value(strategy.get("params"))
    return {
        "source": "base_params",
        "matched": False,
        "target": {},
        "base_params": params,
        "override_params": {},
        "effective_params": params,
    }


def _matching_targeted_params(
    strategy: dict[str, Any],
    *,
    source: str | None,
    symbol: str | None,
    timeframe: str | None,
) -> dict[str, Any] | None:
    if not source or not symbol or not timeframe:
        return None
    profiles = strategy.get(TARGETED_PARAMS_KEY)
    if not isinstance(profiles, list):
        return None
    target = (source, symbol, timeframe)
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        identity = (
            str(profile.get("source") or ""),
            str(profile.get("symbol") or ""),
            str(profile.get("timeframe") or ""),
        )
        if identity == target:
            return profile
    return None


def _target_record(*, source: str | None, symbol: str | None, timeframe: str | None) -> dict[str, str | None]:
    return {
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
    }


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}
