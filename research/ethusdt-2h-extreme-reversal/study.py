from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import math
import random
import statistics
import time
import urllib.parse
import urllib.request
import zipfile
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator


SYMBOL = "ETHUSDT"
INSTRUMENT = "ETHUSDT-PERP"
VENUE = "BINANCE_USDM"
INTERVAL = "2h"
INTERVAL_MS = 2 * 60 * 60 * 1000
LOOKBACK_BARS = 90 * 12
THRESHOLDS = (2.0, 3.0, 4.0)
FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
ARCHIVE_ROOT = "https://data.binance.vision/data/futures/um/monthly/klines"
PHASES = {
    "development": ("2021-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
    "evaluation": ("2024-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
    "confirmation": ("2026-01-01T00:00:00Z", "2026-07-01T00:00:00Z"),
}
COSTS = {
    "favorable": {"fee_each_side": 0.0005, "slippage_each_side": 0.0001},
    "base": {"fee_each_side": 0.0006, "slippage_each_side": 0.0010},
    "stress": {"fee_each_side": 0.0006, "slippage_each_side": 0.0020},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def to_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def iso_from_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def month_iter(start_month: str, end_month: str) -> Iterator[str]:
    current = datetime.strptime(start_month, "%Y-%m")
    end = datetime.strptime(end_month, "%Y-%m")
    while current <= end:
        yield current.strftime("%Y-%m")
        year = current.year + (1 if current.month == 12 else 0)
        month = 1 if current.month == 12 else current.month + 1
        current = current.replace(year=year, month=month)


def month_bounds(start_month: str, end_month: str) -> tuple[int, int]:
    start = datetime.strptime(start_month, "%Y-%m").replace(tzinfo=timezone.utc)
    end_value = datetime.strptime(end_month, "%Y-%m").replace(tzinfo=timezone.utc)
    year = end_value.year + (1 if end_value.month == 12 else 0)
    month = 1 if end_value.month == 12 else end_value.month + 1
    end = end_value.replace(year=year, month=month)
    return to_ms(start), to_ms(end)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def request_bytes(url: str, attempts: int = 4) -> bytes:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Halpha-public-research/1.0"})
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.read()
        except Exception as exc:  # network failures are recorded by the caller
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def archive_url(month: str) -> str:
    filename = f"{SYMBOL}-{INTERVAL}-{month}.zip"
    return f"{ARCHIVE_ROOT}/{SYMBOL}/{INTERVAL}/{filename}"


def fetch_archive(cache_dir: Path, month: str) -> dict[str, object]:
    url = archive_url(month)
    checksum_url = url + ".CHECKSUM"
    filename = url.rsplit("/", 1)[-1]
    relative = Path("klines-2h") / filename
    target = cache_dir / relative
    checksum_text = request_bytes(checksum_url).decode("utf-8").strip()
    expected = checksum_text.split()[0].lower()
    if not target.exists() or sha256_path(target) != expected:
        payload = request_bytes(url)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    actual = sha256_path(target)
    if actual != expected:
        raise RuntimeError(f"checksum mismatch for {month}: expected {expected}, got {actual}")
    return {
        "month": month,
        "url": url,
        "checksum_url": checksum_url,
        "sha256": actual,
        "bytes": target.stat().st_size,
        "cache_relative_path": relative.as_posix(),
    }


def fetch_funding(cache_dir: Path, start_ms: int, end_ms: int, label: str) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    cursor = start_ms
    pages = 0
    while cursor < end_ms:
        query = urllib.parse.urlencode(
            {"symbol": SYMBOL, "startTime": cursor, "endTime": end_ms - 1, "limit": 1000}
        )
        page = json.loads(request_bytes(f"{FUNDING_URL}?{query}").decode("utf-8"))
        pages += 1
        if not page:
            break
        for row in page:
            funding_time = int(row["fundingTime"])
            if start_ms <= funding_time < end_ms:
                rows.append({"fundingTime": funding_time, "fundingRate": str(row["fundingRate"])})
        next_cursor = int(page[-1]["fundingTime"]) + 1
        if next_cursor <= cursor:
            raise RuntimeError("funding pagination did not advance")
        cursor = next_cursor
        if len(page) < 1000:
            break
    unique = {int(row["fundingTime"]): row for row in rows}
    ordered = [unique[key] for key in sorted(unique)]
    relative = Path(f"funding-{label}.json")
    target = cache_dir / relative
    write_json(target, ordered)
    return {
        "url": FUNDING_URL,
        "request_security": "NONE_PUBLIC_MARKET_DATA",
        "requested_start_ms": start_ms,
        "requested_end_exclusive_ms": end_ms,
        "records": len(ordered),
        "pages": pages,
        "first_funding_time": ordered[0]["fundingTime"] if ordered else None,
        "last_funding_time": ordered[-1]["fundingTime"] if ordered else None,
        "sha256": sha256_path(target),
        "bytes": target.stat().st_size,
        "cache_relative_path": relative.as_posix(),
    }


def command_fetch(args: argparse.Namespace) -> None:
    cache_dir = Path(args.cache_dir).resolve()
    start_ms, end_ms = month_bounds(args.start_month, args.end_month)
    archives = [fetch_archive(cache_dir, month) for month in month_iter(args.start_month, args.end_month)]
    label = f"{args.start_month}_{args.end_month}"
    funding = fetch_funding(cache_dir, start_ms, end_ms, label)
    manifest = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "venue": VENUE,
        "exchange_symbol": SYMBOL,
        "instrument": INSTRUMENT,
        "contract": "USDⓈ-M linear perpetual settled in USDT",
        "interval": INTERVAL,
        "timezone": "UTC",
        "cache_root": str(cache_dir),
        "requested_start_month": args.start_month,
        "requested_end_month": args.end_month,
        "archives": archives,
        "funding_snapshot": funding,
        "retrieval_rule": {
            "archive": f"{ARCHIVE_ROOT}/{SYMBOL}/{INTERVAL}/{SYMBOL}-{INTERVAL}-YYYY-MM.zip",
            "archive_integrity": "Verify adjacent official .CHECKSUM SHA-256 before use",
            "funding": f"GET {FUNDING_URL} with symbol={SYMBOL}, ascending pagination",
        },
    }
    manifest["content_identity"] = canonical_digest(
        {"archives": archives, "funding_snapshot": funding, "symbol": SYMBOL, "interval": INTERVAL}
    )
    write_json(Path(args.manifest), manifest)
    print(json.dumps({"archives": len(archives), "funding": funding["records"], "manifest": args.manifest}))


@dataclass(frozen=True)
class Bar:
    open_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


def iter_archive_bars(path: Path) -> Iterator[Bar]:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(names) != 1:
            raise RuntimeError(f"expected one CSV in {path}, found {names}")
        with archive.open(names[0]) as raw:
            rows = csv.reader((line.decode("utf-8") for line in raw))
            for row in rows:
                if not row or not row[0].isdigit():
                    continue
                yield Bar(
                    open_ms=int(row[0]),
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                )


def load_inputs(cache_dir: Path, manifest: dict[str, object]) -> tuple[list[Bar], list[tuple[int, float]]]:
    bars: list[Bar] = []
    for item in manifest["archives"]:  # type: ignore[index]
        path = cache_dir / item["cache_relative_path"]  # type: ignore[index]
        if sha256_path(path) != item["sha256"]:  # type: ignore[index]
            raise RuntimeError(f"archive identity mismatch: {path}")
        bars.extend(iter_archive_bars(path))
    bars.sort(key=lambda bar: bar.open_ms)
    funding_item = manifest["funding_snapshot"]  # type: ignore[index]
    funding_path = cache_dir / funding_item["cache_relative_path"]  # type: ignore[index]
    if sha256_path(funding_path) != funding_item["sha256"]:  # type: ignore[index]
        raise RuntimeError(f"funding identity mismatch: {funding_path}")
    funding_rows = read_json(funding_path)
    funding = [(int(row["fundingTime"]), float(row["fundingRate"])) for row in funding_rows]  # type: ignore[index]
    return bars, funding


def command_inspect(args: argparse.Namespace) -> None:
    manifest = read_json(Path(args.manifest))
    cache_dir = Path(args.cache_dir).resolve()
    bars, funding = load_inputs(cache_dir, manifest)  # type: ignore[arg-type]
    start_ms = to_ms(parse_time(args.start))
    end_ms = to_ms(parse_time(args.end))
    selected = [bar for bar in bars if start_ms <= bar.open_ms < end_ms]
    duplicate_count = len(selected) - len({bar.open_ms for bar in selected})
    gaps = []
    invalid = 0
    for previous, current in zip(selected, selected[1:]):
        if current.open_ms - previous.open_ms != INTERVAL_MS:
            gaps.append({"after": iso_from_ms(previous.open_ms), "before": iso_from_ms(current.open_ms)})
        if min(current.open, current.high, current.low, current.close) <= 0:
            invalid += 1
        if current.high < max(current.open, current.close) or current.low > min(current.open, current.close):
            invalid += 1
    expected = (end_ms - start_ms) // INTERVAL_MS
    funding_selected = [item for item in funding if start_ms <= item[0] < end_ms]
    output = {
        "generated_at": utc_now(),
        "manifest_content_identity": manifest["content_identity"],  # type: ignore[index]
        "start": args.start,
        "end_exclusive": args.end,
        "expected_bars": expected,
        "bars": len(selected),
        "duplicates": duplicate_count,
        "gaps": gaps,
        "invalid_ohlc": invalid,
        "funding_records": len(funding_selected),
        "funding_duplicates": len(funding_selected) - len({item[0] for item in funding_selected}),
        "first_bar": iso_from_ms(selected[0].open_ms) if selected else None,
        "last_bar": iso_from_ms(selected[-1].open_ms) if selected else None,
        "status": "PASS" if len(selected) == expected and not gaps and duplicate_count == 0 and invalid == 0 else "FAIL",
    }
    write_json(Path(args.output), output)
    print(json.dumps({"status": output["status"], "bars": len(selected), "funding": len(funding_selected)}))


def bootstrap_mean_interval(values: list[float], seed: int, reps: int = 4000, block: int = 8) -> list[float | None]:
    if not values:
        return [None, None]
    rng = random.Random(seed)
    n = len(values)
    means: list[float] = []
    for _ in range(reps):
        sample: list[float] = []
        while len(sample) < n:
            start = rng.randrange(n)
            sample.extend(values[(start + offset) % n] for offset in range(block))
        means.append(statistics.fmean(sample[:n]))
    means.sort()
    return [means[int(0.025 * reps)], means[int(0.975 * reps) - 1]]


def max_drawdown_noncompounded(values: Iterable[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)
    return max_drawdown


def summarize(rows: list[dict[str, object]], key: str, seed: int) -> dict[str, object]:
    values = [float(row[key]) for row in rows]
    by_year: dict[str, dict[str, float | int]] = {}
    for year in sorted({str(row["year"]) for row in rows}):
        yearly = [float(row[key]) for row in rows if str(row["year"]) == year]
        by_year[year] = {"count": len(yearly), "mean": statistics.fmean(yearly), "sum": sum(yearly)}
    if not values:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "win_rate": None,
            "sum": 0.0,
            "bootstrap_95pct_mean": [None, None],
            "max_drawdown_noncompounded": None,
            "by_year": by_year,
        }
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "win_rate": sum(value > 0 for value in values) / len(values),
        "sum": sum(values),
        "bootstrap_95pct_mean": bootstrap_mean_interval(values, seed=seed),
        "max_drawdown_noncompounded": max_drawdown_noncompounded(values),
        "by_year": by_year,
    }


def phase_bounds(phase: str) -> tuple[int, int]:
    start, end = PHASES[phase]
    return to_ms(parse_time(start)), to_ms(parse_time(end))


def build_trades(
    bars: list[Bar], funding: list[tuple[int, float]], phase: str, threshold: float
) -> list[dict[str, object]]:
    start_ms, end_ms = phase_bounds(phase)
    returns: list[float | None] = [None]
    for previous, current in zip(bars, bars[1:]):
        returns.append(current.close / previous.close - 1.0)
    funding_events = sorted(((timestamp // INTERVAL_MS) * INTERVAL_MS, rate) for timestamp, rate in funding)
    funding_times = [item[0] for item in funding_events]
    rows: list[dict[str, object]] = []
    for index in range(LOOKBACK_BARS, len(bars) - 1):
        signal_return = returns[index]
        if signal_return is None:
            continue
        history = returns[index - LOOKBACK_BARS : index]
        if any(value is None for value in history):
            continue
        sigma = statistics.stdev(value for value in history if value is not None)
        if sigma <= 0 or abs(signal_return) < threshold * sigma:
            continue
        signal_bar = bars[index]
        trade_bar = bars[index + 1]
        if trade_bar.open_ms != signal_bar.open_ms + INTERVAL_MS:
            continue
        entry_ms = trade_bar.open_ms
        exit_ms = entry_ms + INTERVAL_MS
        if entry_ms < start_ms or exit_ms > end_ms:
            continue
        direction = -1 if signal_return > 0 else 1
        gross = direction * (trade_bar.close / trade_bar.open - 1.0)
        left = bisect.bisect_right(funding_times, entry_ms)
        right = bisect.bisect_right(funding_times, exit_ms)
        mark_notional_ratio = trade_bar.close / trade_bar.open
        funding_component = sum(
            -direction * rate * mark_notional_ratio for _, rate in funding_events[left:right]
        )
        row: dict[str, object] = {
            "signal_time": iso_from_ms(signal_bar.open_ms + INTERVAL_MS),
            "entry_time": iso_from_ms(entry_ms),
            "exit_time": iso_from_ms(exit_ms),
            "year": datetime.fromtimestamp(entry_ms / 1000, tz=timezone.utc).year,
            "side": "LONG" if direction == 1 else "SHORT",
            "signal_return": signal_return,
            "rolling_sigma": sigma,
            "signal_sigma": abs(signal_return) / sigma,
            "gross": gross,
            "funding": funding_component,
        }
        for name, costs in COSTS.items():
            round_trip = 2 * (costs["fee_each_side"] + costs["slippage_each_side"])
            row[f"net_{name}"] = gross + funding_component - round_trip
            row[f"momentum_net_{name}"] = -gross - funding_component - round_trip
        rows.append(row)
    return rows


def autocorrelation(values: list[float]) -> float | None:
    if len(values) < 3:
        return None
    left = values[:-1]
    right = values[1:]
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    denominator = math.sqrt(
        sum((x - left_mean) ** 2 for x in left) * sum((y - right_mean) ** 2 for y in right)
    )
    return numerator / denominator if denominator else None


def selected_threshold(path: str) -> float:
    selection = read_json(Path(path))
    value = selection.get("selected_threshold_sigma")  # type: ignore[union-attr]
    if value is None:
        raise RuntimeError("development gate did not select a threshold; holdout must remain unopened")
    return float(value)


def command_analyze(args: argparse.Namespace) -> None:
    manifest = read_json(Path(args.manifest))
    cache_dir = Path(args.cache_dir).resolve()
    bars, funding = load_inputs(cache_dir, manifest)  # type: ignore[arg-type]
    if args.phase == "development":
        thresholds = THRESHOLDS
    else:
        if not args.selection:
            raise RuntimeError("evaluation and confirmation require --selection")
        thresholds = (selected_threshold(args.selection),)
    start_ms, end_ms = phase_bounds(args.phase)
    phase_bars = [bar for bar in bars if start_ms <= bar.open_ms < end_ms]
    phase_returns = [current.close / previous.close - 1.0 for previous, current in zip(phase_bars, phase_bars[1:])]
    variants: dict[str, object] = {}
    for threshold in thresholds:
        rows = build_trades(bars, funding, args.phase, threshold)
        key = f"{threshold:g}sigma"
        variants[key] = {
            "threshold_sigma": threshold,
            "long_count": sum(row["side"] == "LONG" for row in rows),
            "short_count": sum(row["side"] == "SHORT" for row in rows),
            "gross": summarize(rows, "gross", seed=20260720 + int(threshold * 10)),
            "funding_sum": sum(float(row["funding"]) for row in rows),
            "favorable": summarize(rows, "net_favorable", seed=20260820 + int(threshold * 10)),
            "base": summarize(rows, "net_base", seed=20260920 + int(threshold * 10)),
            "stress": summarize(rows, "net_stress", seed=20261020 + int(threshold * 10)),
            "momentum_base": summarize(rows, "momentum_net_base", seed=20261120 + int(threshold * 10)),
            "trade_rows_digest": canonical_digest(rows),
        }
    output = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "phase": args.phase,
        "period": {"start": PHASES[args.phase][0], "end_exclusive": PHASES[args.phase][1]},
        "manifest_content_identity": manifest["content_identity"],  # type: ignore[index]
        "study_code_sha256": sha256_path(Path(__file__)),
        "rules": {
            "timeframe": INTERVAL,
            "lookback_bars": LOOKBACK_BARS,
            "thresholds_sigma": list(thresholds),
            "entry": "next 2h bar open after completed signal bar",
            "exit": "same trade bar close",
            "direction": "contrarian",
            "funding": "actual rate; fundingTime normalized to its 2h settlement boundary; entry < boundary <= exit; trade close proxies mark notional",
            "costs": COSTS,
        },
        "phase_return_lag1_autocorrelation": autocorrelation(phase_returns),
        "phase_buy_and_hold_return": phase_bars[-1].close / phase_bars[0].open - 1.0 if phase_bars else None,
        "variants": variants,
    }
    output["content_digest"] = canonical_digest({key: value for key, value in output.items() if key != "generated_at"})
    write_json(Path(args.output), output)
    print(json.dumps({"phase": args.phase, "variants": {k: v["base"]["mean"] for k, v in variants.items()}}))


def command_select(args: argparse.Namespace) -> None:
    development = read_json(Path(args.development))
    candidates: list[dict[str, object]] = []
    for key, metrics in development["variants"].items():  # type: ignore[index,union-attr]
        base = metrics["base"]
        yearly = base["by_year"]
        positive_years = sum(
            item["mean"] is not None and float(item["mean"]) > 0 for item in yearly.values()
        )
        ci_low = base["bootstrap_95pct_mean"][0]
        mean = base["mean"]
        passed = (
            int(base["count"]) >= 60
            and mean is not None
            and float(mean) > 0
            and positive_years >= 2
            and ci_low is not None
            and float(ci_low) > 0
        )
        candidates.append(
            {
                "variant": key,
                "threshold_sigma": metrics["threshold_sigma"],
                "count": base["count"],
                "mean": mean,
                "bootstrap_95pct_mean_low": ci_low,
                "positive_development_years": positive_years,
                "passed": passed,
            }
        )
    passers = [item for item in candidates if item["passed"]]
    passers.sort(key=lambda item: (float(item["bootstrap_95pct_mean_low"]), float(item["mean"])), reverse=True)
    selected = passers[0] if passers else None
    output = {
        "generated_at": utc_now(),
        "development_content_digest": development["content_digest"],  # type: ignore[index]
        "gate": "count >= 60; base mean > 0; at least two positive calendar years; 8-trade block-bootstrap 95% lower mean > 0",
        "candidates": candidates,
        "selection_status": "PASSED_DEVELOPMENT_GATE" if selected else "NO_VARIANT_PASSED_DEVELOPMENT_GATE_STOP",
        "selected_threshold_sigma": selected["threshold_sigma"] if selected else None,
        "holdout_authorized": bool(selected),
    }
    output["content_digest"] = canonical_digest({key: value for key, value in output.items() if key != "generated_at"})
    write_json(Path(args.output), output)
    print(json.dumps({"status": output["selection_status"], "selected": output["selected_threshold_sigma"]}))


def command_combine(args: argparse.Namespace) -> None:
    development = read_json(Path(args.development))
    selection = read_json(Path(args.selection))
    evaluation = read_json(Path(args.evaluation))
    confirmation = read_json(Path(args.confirmation))
    threshold = selection["selected_threshold_sigma"]  # type: ignore[index]
    if threshold is None:
        raise RuntimeError("cannot combine without a passed development gate")
    key = f"{float(threshold):g}sigma"
    dev = development["variants"][key]["base"]  # type: ignore[index]
    eva = evaluation["variants"][key]["base"]  # type: ignore[index]
    con = confirmation["variants"][key]["base"]  # type: ignore[index]
    eva_years = eva["by_year"]
    eva_mean = eva["mean"]
    con_mean = con["mean"]
    evaluation_support = (
        int(eva["count"]) >= 40
        and eva_mean is not None
        and float(eva_mean) > 0
        and set(eva_years) == {"2024", "2025"}
        and all(float(item["mean"]) > 0 for item in eva_years.values())
        and eva["bootstrap_95pct_mean"][0] is not None
        and float(eva["bootstrap_95pct_mean"][0]) > 0
    )
    confirmation_support = int(con["count"]) >= 10 and con_mean is not None and float(con_mean) > 0
    if evaluation_support and confirmation_support:
        conclusion = "SUPPORTS_WITHIN_SCOPE"
    elif int(eva["count"]) >= 40 and eva_mean is not None and float(eva_mean) <= 0:
        conclusion = "DOES_NOT_SUPPORT"
    else:
        conclusion = "INSUFFICIENT_EVIDENCE"
    output = {
        "generated_at": utc_now(),
        "conclusion": conclusion,
        "scope": "ETHUSDT 2h one-period extreme-return reversal under fixed rolling-volatility rule and modeled costs",
        "selected_threshold_sigma": threshold,
        "development": dev,
        "evaluation": eva,
        "confirmation": con,
        "evaluation_support_gate": evaluation_support,
        "confirmation_support_gate": confirmation_support,
        "formal_product_strategy_comparison": "NOT_RUN_NO_FAIR_EXACT_REPLAY_WITHOUT_SECOND_IMPLEMENTATION",
        "product_effects": "NONE",
    }
    output["content_digest"] = canonical_digest({key: value for key, value in output.items() if key != "generated_at"})
    write_json(Path(args.output), output)
    print(json.dumps({"conclusion": conclusion, "threshold_sigma": threshold}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ETHUSDT 2h extreme-return reversal study")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch = subparsers.add_parser("fetch")
    fetch.add_argument("--cache-dir", required=True)
    fetch.add_argument("--start-month", required=True)
    fetch.add_argument("--end-month", required=True)
    fetch.add_argument("--manifest", required=True)
    fetch.set_defaults(func=command_fetch)

    inspect = subparsers.add_parser("inspect")
    inspect.add_argument("--cache-dir", required=True)
    inspect.add_argument("--manifest", required=True)
    inspect.add_argument("--start", required=True)
    inspect.add_argument("--end", required=True)
    inspect.add_argument("--output", required=True)
    inspect.set_defaults(func=command_inspect)

    analyze = subparsers.add_parser("analyze")
    analyze.add_argument("--cache-dir", required=True)
    analyze.add_argument("--manifest", required=True)
    analyze.add_argument("--phase", choices=tuple(PHASES), required=True)
    analyze.add_argument("--selection")
    analyze.add_argument("--output", required=True)
    analyze.set_defaults(func=command_analyze)

    select = subparsers.add_parser("select")
    select.add_argument("--development", required=True)
    select.add_argument("--output", required=True)
    select.set_defaults(func=command_select)

    combine = subparsers.add_parser("combine")
    combine.add_argument("--development", required=True)
    combine.add_argument("--selection", required=True)
    combine.add_argument("--evaluation", required=True)
    combine.add_argument("--confirmation", required=True)
    combine.add_argument("--output", required=True)
    combine.set_defaults(func=command_combine)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
