"""Reproducible entry-selectivity study for the one-shot BTCUSDT strategy.

The script reads only public Binance archives from an explicit cache root.  It
does not import Halpha product code, connect to a product database, or call a
trading endpoint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numba as nb
import numpy as np
import pandas as pd
import vectorbt as vbt


LOOKBACKS = (4, 12, 20, 32, 48, 64)
CONFIRMATIONS = (1, 2, 3)
EXTENSIONS = (0.25, 0.5)
DIRECTIONS = (1, -1)
SCENARIOS = {
    "favorable": (0.0004, 0.0002),
    "base": (0.0004, 0.0010),
    "stress": (0.0004, 0.0015),
}
PERIODS = {
    "development": ("2021-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
    "evaluation": ("2024-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
    "confirmation": ("2026-01-01T00:00:00Z", "2026-07-01T00:00:00Z"),
}
DEFAULT = (20, 2, 0.5)
CSV_COLUMNS = ("open_time", "open", "high", "low", "close", "volume")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _utc_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def _month_key(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).strftime("%Y-%m")


@dataclass(frozen=True)
class MarketData:
    open_time: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    funding_rate: np.ndarray
    funding_mark: np.ndarray
    manifest_identity: str
    data_quality: dict[str, Any]


def _load_market_data(
    *,
    cache_root: Path,
    manifest_path: Path,
    start_ms: int,
    end_ms: int,
) -> MarketData:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    warmup_start = start_ms - 2 * 24 * 60 * 60 * 1000
    horizon_end = end_ms + 61 * 60 * 1000
    start_month = _month_key(warmup_start)
    end_month = _month_key(horizon_end - 1)
    archives = [
        item
        for item in manifest["archives"]
        if start_month <= item["month"] <= end_month
    ]
    if not archives:
        raise ValueError("NO_ARCHIVES_FOR_PERIOD")

    frames: list[pd.DataFrame] = []
    verified: list[dict[str, Any]] = []
    for item in archives:
        archive = cache_root / item["cache_relative_path"]
        if not archive.is_file():
            raise FileNotFoundError(archive)
        actual_sha = _sha256(archive)
        if actual_sha != item["sha256"]:
            raise ValueError(f"ARCHIVE_SHA256_MISMATCH:{archive.name}")
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            if len(names) != 1:
                raise ValueError(f"ARCHIVE_MEMBER_COUNT_INVALID:{archive.name}")
            with bundle.open(names[0]) as source:
                first_line = source.readline().strip().lower()
                source.seek(0)
                skiprows = 1 if first_line.startswith(b"open_time") else 0
                frame = pd.read_csv(
                    source,
                    header=None,
                    skiprows=skiprows,
                    usecols=range(6),
                    names=CSV_COLUMNS,
                    dtype={
                        "open_time": "int64",
                        "open": "float64",
                        "high": "float64",
                        "low": "float64",
                        "close": "float64",
                        "volume": "float64",
                    },
                )
        frames.append(frame)
        verified.append(
            {"month": item["month"], "sha256": actual_sha, "bytes": archive.stat().st_size}
        )

    bars = pd.concat(frames, ignore_index=True)
    bars = bars.loc[
        (bars["open_time"] >= warmup_start) & (bars["open_time"] < horizon_end)
    ].sort_values("open_time", kind="stable")
    bars = bars.drop_duplicates("open_time", keep=False).reset_index(drop=True)
    if bars.empty:
        raise ValueError("NO_BARS_FOR_PERIOD")

    open_time = bars["open_time"].to_numpy(dtype=np.int64, copy=True)
    diffs = np.diff(open_time)
    if np.any(diffs != 60_000):
        raise ValueError("BAR_TIMELINE_NOT_CONTINUOUS")
    open_price = bars["open"].to_numpy(dtype=np.float64, copy=True)
    high = bars["high"].to_numpy(dtype=np.float64, copy=True)
    low = bars["low"].to_numpy(dtype=np.float64, copy=True)
    close = bars["close"].to_numpy(dtype=np.float64, copy=True)
    volume = bars["volume"].to_numpy(dtype=np.float64, copy=True)
    if (
        np.any(~np.isfinite(open_price))
        or np.any(~np.isfinite(high))
        or np.any(~np.isfinite(low))
        or np.any(~np.isfinite(close))
        or np.any(open_price <= 0)
        or np.any(low <= 0)
        or np.any(high < np.maximum(open_price, close))
        or np.any(low > np.minimum(open_price, close))
    ):
        raise ValueError("BAR_OHLC_INVALID")

    funding_info = manifest["funding_snapshot"]
    funding_path = cache_root / funding_info["cache_relative_path"]
    if _sha256(funding_path) != funding_info["sha256"]:
        raise ValueError("FUNDING_SHA256_MISMATCH")
    funding_records = json.loads(funding_path.read_text(encoding="utf-8"))
    funding_rate = np.zeros(len(bars), dtype=np.float64)
    funding_mark = np.zeros(len(bars), dtype=np.float64)
    first_ms = int(open_time[0])
    for record in funding_records:
        event_ms = int(record["fundingTime"])
        minute_ms = event_ms - event_ms % 60_000
        index = (minute_ms - first_ms) // 60_000
        if index < 0 or index >= len(bars) or open_time[index] != minute_ms:
            continue
        funding_rate[index] += float(record["fundingRate"])
        mark_text = str(record.get("markPrice", "")).strip()
        funding_mark[index] = float(mark_text) if mark_text else open_price[index]

    quality = {
        "bars": int(len(bars)),
        "first_open_time": datetime.fromtimestamp(open_time[0] / 1000, tz=UTC).isoformat(),
        "last_open_time": datetime.fromtimestamp(open_time[-1] / 1000, tz=UTC).isoformat(),
        "archives_verified": len(verified),
        "archive_bytes": int(sum(item["bytes"] for item in verified)),
        "funding_events_in_loaded_range": int(np.count_nonzero(funding_rate)),
        "continuous_1m": True,
        "valid_ohlc": True,
    }
    identity = _json_digest(
        {
            "manifest_sha256": _sha256(manifest_path),
            "archives": verified,
            "funding_sha256": funding_info["sha256"],
        }
    )
    return MarketData(
        open_time=open_time,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
        funding_rate=funding_rate,
        funding_mark=funding_mark,
        manifest_identity=identity,
        data_quality=quality,
    )


def _target_indicators(data: MarketData, lookback: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    group = data.open_time // 900_000
    target = pd.DataFrame(
        {
            "group": group,
            "high": data.high,
            "low": data.low,
            "close": data.close,
        }
    ).groupby("group", sort=True, observed=True).agg(
        high=("high", "max"), low=("low", "min"), close=("close", "last")
    )
    previous_close = target["close"].shift(1)
    true_range = pd.concat(
        [
            target["high"] - target["low"],
            (target["high"] - previous_close).abs(),
            (target["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    upper = target["high"].rolling(lookback, min_periods=lookback).max()
    lower = target["low"].rolling(lookback, min_periods=lookback).min()

    first_group = int(target.index[0])
    target_upper = upper.to_numpy(dtype=np.float64)
    target_lower = lower.to_numpy(dtype=np.float64)
    target_atr = atr.to_numpy(dtype=np.float64)
    source_index = group - 1 - first_group
    valid = (source_index >= 0) & (source_index < len(target))
    mapped_upper = np.full(len(group), np.nan, dtype=np.float64)
    mapped_lower = np.full(len(group), np.nan, dtype=np.float64)
    mapped_atr = np.full(len(group), np.nan, dtype=np.float64)
    mapped_upper[valid] = target_upper[source_index[valid]]
    mapped_lower[valid] = target_lower[source_index[valid]]
    mapped_atr[valid] = target_atr[source_index[valid]]
    return mapped_upper, mapped_lower, mapped_atr


def _trigger_indices(
    data: MarketData,
    *,
    upper: np.ndarray,
    lower: np.ndarray,
    atr: np.ndarray,
    confirmation: int,
    extension: float,
    direction: int,
    start_ms: int,
    end_ms: int,
) -> np.ndarray:
    position = (data.open_time % 900_000) // 60_000
    valid = (
        (position >= confirmation - 1)
        & (position <= 13)
        & np.isfinite(upper)
        & np.isfinite(lower)
        & np.isfinite(atr)
        & (atr > 0)
        & (data.open_time >= start_ms)
        & (data.open_time + 61 * 60_000 < end_ms)
    )
    crossed = valid.copy()
    for offset in range(confirmation):
        shifted = np.empty_like(data.close)
        shifted[:offset] = np.nan
        shifted[offset:] = data.close[: len(data.close) - offset]
        if direction == 1:
            crossed &= shifted > upper
        else:
            crossed &= shifted < lower
    if direction == 1:
        crossed &= data.close <= upper + extension * atr
    else:
        crossed &= data.close >= lower - extension * atr
    return np.flatnonzero(crossed).astype(np.int64)


@nb.njit(cache=True)
def _simulate(
    trigger_indices: np.ndarray,
    open_price: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    funding_rate: np.ndarray,
    funding_mark: np.ndarray,
    atr: np.ndarray,
    boundary: np.ndarray,
    direction: int,
    fee: float,
    adverse_execution: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    returns = np.empty(len(trigger_indices), dtype=np.float64)
    entries = np.empty(len(trigger_indices), dtype=np.int64)
    exits = np.empty(len(trigger_indices), dtype=np.int64)
    count = 0
    next_trigger = 0
    for trigger in trigger_indices:
        if trigger < next_trigger:
            continue
        entry_index = trigger + 1
        time_exit_index = entry_index + 60
        if time_exit_index >= len(open_price):
            break
        raw_entry = open_price[entry_index]
        conservative_entry = raw_entry * (1.0 + direction * adverse_execution)
        if direction == 1 and conservative_entry > boundary[trigger]:
            continue
        if direction == -1 and conservative_entry < boundary[trigger]:
            continue
        entry_fill = conservative_entry
        risk = 1.5 * atr[trigger]
        stop = entry_fill - direction * risk
        tp1 = entry_fill + direction * risk * 1.5
        tp2 = entry_fill + direction * risk * 3.0
        remaining = 1.0
        pnl = -fee * entry_fill / raw_entry
        exited_at = time_exit_index

        for minute in range(entry_index, time_exit_index):
            if minute > entry_index and funding_rate[minute] != 0.0:
                mark = funding_mark[minute]
                if mark <= 0.0:
                    mark = open_price[minute]
                pnl += -direction * funding_rate[minute] * remaining * mark / raw_entry

            if direction == 1:
                stop_hit = low[minute] <= stop
                tp1_hit = remaining > 0.5 and high[minute] >= tp1
                tp2_hit = high[minute] >= tp2
            else:
                stop_hit = high[minute] >= stop
                tp1_hit = remaining > 0.5 and low[minute] <= tp1
                tp2_hit = low[minute] <= tp2

            if stop_hit:
                raw_fill = stop
                if direction == 1 and open_price[minute] < stop:
                    raw_fill = open_price[minute]
                elif direction == -1 and open_price[minute] > stop:
                    raw_fill = open_price[minute]
                exit_fill = raw_fill * (1.0 - direction * adverse_execution)
                pnl += direction * (exit_fill - entry_fill) * remaining / raw_entry
                pnl -= fee * exit_fill * remaining / raw_entry
                remaining = 0.0
                exited_at = minute
                break

            if tp1_hit:
                fraction = 0.5
                exit_fill = tp1 * (1.0 - direction * adverse_execution)
                pnl += direction * (exit_fill - entry_fill) * fraction / raw_entry
                pnl -= fee * exit_fill * fraction / raw_entry
                remaining -= fraction
            if tp2_hit and remaining > 0.0:
                exit_fill = tp2 * (1.0 - direction * adverse_execution)
                pnl += direction * (exit_fill - entry_fill) * remaining / raw_entry
                pnl -= fee * exit_fill * remaining / raw_entry
                remaining = 0.0
                exited_at = minute
                break

        if remaining > 0.0:
            raw_fill = open_price[time_exit_index]
            exit_fill = raw_fill * (1.0 - direction * adverse_execution)
            pnl += direction * (exit_fill - entry_fill) * remaining / raw_entry
            pnl -= fee * exit_fill * remaining / raw_entry
        returns[count] = pnl
        entries[count] = entry_index
        exits[count] = exited_at
        count += 1
        next_trigger = exited_at + 1
    return returns[:count], entries[:count], exits[:count]


def _metrics(returns: np.ndarray, entry_times: np.ndarray) -> dict[str, Any]:
    if len(returns) == 0:
        return {
            "trades": 0,
            "mean": None,
            "median": None,
            "win_rate": None,
            "total_compound": None,
            "max_drawdown": None,
            "standard_error": None,
            "annual_means": {},
        }
    equity = np.cumprod(1.0 + returns)
    peak = np.maximum.accumulate(np.concatenate(([1.0], equity)))
    curve = np.concatenate(([1.0], equity))
    drawdown = curve / peak - 1.0
    years = pd.to_datetime(entry_times, unit="ms", utc=True).year.to_numpy()
    annual = {
        str(int(year)): float(np.mean(returns[years == year]))
        for year in np.unique(years)
    }
    standard_error = (
        float(np.std(returns, ddof=1) / math.sqrt(len(returns)))
        if len(returns) > 1
        else None
    )
    return {
        "trades": int(len(returns)),
        "mean": float(np.mean(returns)),
        "median": float(np.median(returns)),
        "win_rate": float(np.mean(returns > 0)),
        "total_compound": float(equity[-1] - 1.0),
        "max_drawdown": float(np.min(drawdown)),
        "standard_error": standard_error,
        "annual_means": annual,
    }


def _config_key(lookback: int, confirmation: int, extension: float, direction: int) -> str:
    side = "LONG" if direction == 1 else "SHORT"
    return f"{side}:{lookback}:{confirmation}:{extension:g}"


def _run_config(
    data: MarketData,
    *,
    lookback: int,
    confirmation: int,
    extension: float,
    direction: int,
    start_ms: int,
    end_ms: int,
    indicators: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None,
) -> dict[str, Any]:
    upper, lower, atr = indicators or _target_indicators(data, lookback)
    triggers = _trigger_indices(
        data,
        upper=upper,
        lower=lower,
        atr=atr,
        confirmation=confirmation,
        extension=extension,
        direction=direction,
        start_ms=start_ms,
        end_ms=end_ms,
    )
    boundary = upper + extension * atr if direction == 1 else lower - extension * atr
    result: dict[str, Any] = {
        "config_id": _config_key(lookback, confirmation, extension, direction),
        "direction": "LONG" if direction == 1 else "SHORT",
        "channel_lookback_15m": lookback,
        "confirmation_bars_1m": confirmation,
        "max_entry_extension_atr": extension,
        "raw_trigger_count": int(len(triggers)),
    }
    for name, (fee, adverse) in SCENARIOS.items():
        returns, entry_indices, _ = _simulate(
            triggers,
            data.open,
            data.high,
            data.low,
            data.funding_rate,
            data.funding_mark,
            atr,
            boundary,
            direction,
            fee,
            adverse,
        )
        result[name] = _metrics(returns, data.open_time[entry_indices])
    return result


def _flatten(result: dict[str, Any], *, selected: bool) -> dict[str, Any]:
    row = {
        "config_id": result["config_id"],
        "selected_candidate": selected,
        "direction": result["direction"],
        "channel_lookback_15m": result["channel_lookback_15m"],
        "confirmation_bars_1m": result["confirmation_bars_1m"],
        "max_entry_extension_atr": result["max_entry_extension_atr"],
        "raw_trigger_count": result["raw_trigger_count"],
    }
    for scenario in SCENARIOS:
        metrics = result[scenario]
        for key in (
            "trades",
            "mean",
            "median",
            "win_rate",
            "total_compound",
            "max_drawdown",
            "standard_error",
        ):
            row[f"{scenario}_{key}"] = metrics[key]
        for year, value in metrics["annual_means"].items():
            row[f"{scenario}_mean_{year}"] = value
    return row


def _configs_for_phase(phase: str, authorization: dict[str, Any] | None) -> list[tuple[int, int, float, int, bool]]:
    if phase == "development":
        return [
            (lookback, confirmation, extension, direction, True)
            for lookback in LOOKBACKS
            for confirmation in CONFIRMATIONS
            for extension in EXTENSIONS
            for direction in DIRECTIONS
        ]
    if authorization is None:
        raise ValueError("AUTHORIZATION_REQUIRED")
    key = "selected_candidates" if phase == "evaluation" else "confirmation_candidate"
    raw = authorization.get(key)
    candidates = raw if isinstance(raw, list) else ([raw] if isinstance(raw, dict) else [])
    if not candidates:
        raise ValueError("AUTHORIZED_CANDIDATE_MISSING")
    configs: list[tuple[int, int, float, int, bool]] = []
    for item in candidates:
        direction = 1 if item["direction"] == "LONG" else -1
        configs.append(
            (
                int(item["channel_lookback_15m"]),
                int(item["confirmation_bars_1m"]),
                float(item["max_entry_extension_atr"]),
                direction,
                True,
            )
        )
    for direction in DIRECTIONS:
        default = (*DEFAULT, direction, False)
        if not any(item[:4] == default[:4] for item in configs):
            configs.append(default)
    return configs


def analyze(args: argparse.Namespace) -> None:
    start_text, end_text = PERIODS[args.phase]
    start_ms, end_ms = _utc_ms(start_text), _utc_ms(end_text)
    authorization = (
        json.loads(Path(args.authorization).read_text(encoding="utf-8"))
        if args.authorization
        else None
    )
    configs = _configs_for_phase(args.phase, authorization)
    data = _load_market_data(
        cache_root=Path(args.cache_root),
        manifest_path=Path(args.manifest),
        start_ms=start_ms,
        end_ms=end_ms,
    )
    indicator_cache: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    rows: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []
    for lookback, confirmation, extension, direction, selected in configs:
        if lookback not in indicator_cache:
            indicator_cache[lookback] = _target_indicators(data, lookback)
        indicators = indicator_cache[lookback]
        result = _run_config(
            data,
            lookback=lookback,
            confirmation=confirmation,
            extension=extension,
            direction=direction,
            start_ms=start_ms,
            end_ms=end_ms,
            indicators=indicators,
        )
        details.append(result)
        rows.append(_flatten(result, selected=selected))

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{args.phase}.csv"
    json_path = output_dir / f"{args.phase}.json"
    pd.DataFrame(rows).sort_values("config_id").to_csv(csv_path, index=False)
    payload = {
        "schema_version": 1,
        "phase": args.phase,
        "period": [start_text, end_text],
        "generated_at": datetime.now(UTC).isoformat(),
        "framework": {
            "vectorbt": vbt.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "numba": nb.__version__,
        },
        "data_identity": data.manifest_identity,
        "data_quality": data.data_quality,
        "authorization_sha256": _sha256(Path(args.authorization)) if args.authorization else None,
        "configuration_count": len(rows),
        "csv_sha256": _sha256(csv_path),
        "results": details,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"phase": args.phase, "rows": len(rows), "csv": str(csv_path), "json": str(json_path)}))


def _candidate_from_row(row: pd.Series) -> dict[str, Any]:
    return {
        "config_id": str(row["config_id"]),
        "direction": str(row["direction"]),
        "channel_lookback_15m": int(row["channel_lookback_15m"]),
        "confirmation_bars_1m": int(row["confirmation_bars_1m"]),
        "max_entry_extension_atr": float(row["max_entry_extension_atr"]),
    }


def select_development(args: argparse.Namespace) -> None:
    source = Path(args.input)
    frame = pd.read_csv(source)
    required_years = (2021, 2022, 2023)
    passed: list[pd.Series] = []
    for _, row in frame.iterrows():
        annual = [float(row.get(f"base_mean_{year}", np.nan)) for year in required_years]
        if (
            int(row["base_trades"]) >= 100
            and float(row["base_mean"]) > 0
            and float(row["stress_mean"]) > 0
            and sum(value > 0 for value in annual if np.isfinite(value)) >= 2
            and min(annual) >= -0.001
        ):
            row = row.copy()
            row["worst_annual_base_mean"] = min(annual)
            passed.append(row)
    passed.sort(
        key=lambda row: (
            -float(row["worst_annual_base_mean"]),
            -float(row["stress_mean"]),
            -float(row["base_mean"]),
            -int(row["channel_lookback_15m"]),
            -int(row["confirmation_bars_1m"]),
            float(row["max_entry_extension_atr"]),
        )
    )
    selected = [_candidate_from_row(row) for row in passed[:3]]
    payload = {
        "schema_version": 1,
        "phase": "development_selection",
        "generated_at": datetime.now(UTC).isoformat(),
        "input_sha256": _sha256(source),
        "gate_pass_count": len(passed),
        "selected_candidates": selected,
        "evaluation_authorized": bool(selected),
        "stop_reason": None if selected else "NO_CONFIGURATION_PASSED_DEVELOPMENT_GATE",
    }
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))


def qualify_evaluation(args: argparse.Namespace) -> None:
    source = Path(args.input)
    frame = pd.read_csv(source)
    candidates = frame.loc[frame["selected_candidate"] == True].copy()  # noqa: E712
    passers: list[pd.Series] = []
    for _, row in candidates.iterrows():
        default = frame.loc[
            (frame["direction"] == row["direction"])
            & (frame["channel_lookback_15m"] == DEFAULT[0])
            & (frame["confirmation_bars_1m"] == DEFAULT[1])
            & (frame["max_entry_extension_atr"] == DEFAULT[2])
        ]
        if default.empty:
            raise ValueError("DEFAULT_BENCHMARK_MISSING")
        delta = float(row["base_mean"]) - float(default.iloc[0]["base_mean"])
        if (
            int(row["base_trades"]) >= 60
            and float(row["base_mean"]) > 0
            and float(row["stress_mean"]) > 0
            and float(row.get("base_mean_2024", np.nan)) > 0
            and float(row.get("base_mean_2025", np.nan)) > 0
            and delta >= 0.0005
        ):
            passers.append(row)
    candidate = _candidate_from_row(passers[0]) if passers else None
    payload = {
        "schema_version": 1,
        "phase": "evaluation_gate",
        "generated_at": datetime.now(UTC).isoformat(),
        "input_sha256": _sha256(source),
        "pass_count": len(passers),
        "confirmation_candidate": candidate,
        "confirmation_authorized": candidate is not None,
        "stop_reason": None if candidate else "NO_FIXED_CANDIDATE_PASSED_EVALUATION_GATE",
    }
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("--phase", choices=tuple(PERIODS), required=True)
    analyze_parser.add_argument("--cache-root", required=True)
    analyze_parser.add_argument("--manifest", required=True)
    analyze_parser.add_argument("--output-dir", required=True)
    analyze_parser.add_argument("--authorization")
    analyze_parser.set_defaults(func=analyze)

    select_parser = subparsers.add_parser("select-development")
    select_parser.add_argument("--input", required=True)
    select_parser.add_argument("--output", required=True)
    select_parser.set_defaults(func=select_development)

    evaluation_parser = subparsers.add_parser("qualify-evaluation")
    evaluation_parser.add_argument("--input", required=True)
    evaluation_parser.add_argument("--output", required=True)
    evaluation_parser.set_defaults(func=qualify_evaluation)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
