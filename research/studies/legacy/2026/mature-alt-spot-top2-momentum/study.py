from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


SYMBOLS = ("XRPUSDT", "ADAUSDT", "LTCUSDT", "LINKUSDT", "DOGEUSDT")
ARCHIVE_ROOT = "https://data.binance.vision/data/spot/monthly/klines"
KLINE_URL = "https://data-api.binance.vision/api/v3/klines"
DAY_MS = 86_400_000
LOOKBACKS = (60, 90, 120)
PRIMARY_LOOKBACK = 90
MAX_HOLDINGS = 2
COSTS = {"favorable": 0.0006, "base": 0.0016, "stress": 0.0026}
PHASES = {
    "development": ("2021-01-01T00:00:00Z", "2023-01-01T00:00:00Z"),
    "evaluation": ("2023-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
    "confirmation": ("2025-01-01T00:00:00Z", "2026-07-01T00:00:00Z"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def to_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def next_month(value: datetime) -> datetime:
    return value.replace(year=value.year + (value.month == 12), month=1 if value.month == 12 else value.month + 1)


def month_iter(start: str, end: str):
    current = datetime.strptime(start, "%Y-%m")
    final = datetime.strptime(end, "%Y-%m")
    while current <= final:
        yield current.strftime("%Y-%m")
        current = next_month(current)


def month_bounds(start: str, end: str) -> tuple[int, int]:
    first = datetime.strptime(start, "%Y-%m").replace(tzinfo=timezone.utc)
    final = next_month(datetime.strptime(end, "%Y-%m")).replace(tzinfo=timezone.utc)
    return int(first.timestamp() * 1000), int(final.timestamp() * 1000)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def request_bytes(url: str, attempts: int = 4) -> bytes:
    error = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Halpha-public-research/1.0"})
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.read()
        except Exception as exc:
            error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"request failed: {url}") from error


def normalize_open_ms(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    return numeric.where(numeric < 100_000_000_000_000, numeric // 1000)


def fetch_archive(cache: Path, symbol: str, month: str) -> dict[str, object]:
    filename = f"{symbol}-1d-{month}.zip"
    url = f"{ARCHIVE_ROOT}/{symbol}/1d/{filename}"
    expected = request_bytes(url + ".CHECKSUM").decode("utf-8").split()[0].lower()
    relative = Path(symbol) / "klines-1d" / filename
    target = cache / relative
    if not target.exists() or sha256_path(target) != expected:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(request_bytes(url))
    actual = sha256_path(target)
    if actual != expected:
        raise RuntimeError(f"checksum mismatch: {symbol} {month}")
    return {
        "symbol": symbol,
        "month": month,
        "url": url,
        "checksum_url": url + ".CHECKSUM",
        "sha256": actual,
        "bytes": target.stat().st_size,
        "cache_relative_path": relative.as_posix(),
    }


def fetch_backfill(
    cache: Path,
    symbol: str,
    start_ms: int,
    end_ms: int,
    label: str,
    archives: list[dict[str, object]],
) -> dict[str, object]:
    archive_times: set[int] = set()
    for item in archives:
        path = cache / str(item["cache_relative_path"])
        frame = pd.read_csv(path, compression="zip", header=None, usecols=[0])
        archive_times.update(normalize_open_ms(frame.iloc[:, 0]).dropna().astype("int64").tolist())

    api_rows: dict[int, dict[str, object]] = {}
    cursor = start_ms
    pages = 0
    while cursor < end_ms:
        query = urllib.parse.urlencode(
            {"symbol": symbol, "interval": "1d", "startTime": cursor, "endTime": end_ms - 1, "limit": 1000}
        )
        page = json.loads(request_bytes(f"{KLINE_URL}?{query}").decode("utf-8"))
        pages += 1
        if not page:
            break
        for row in page:
            open_ms = int(row[0])
            if start_ms <= open_ms < end_ms:
                api_rows[open_ms] = {
                    "open_ms": open_ms,
                    "open": str(row[1]),
                    "high": str(row[2]),
                    "low": str(row[3]),
                    "close": str(row[4]),
                    "volume": str(row[5]),
                    "quote_volume": str(row[7]),
                }
        next_cursor = int(page[-1][0]) + DAY_MS
        if next_cursor <= cursor:
            raise RuntimeError("kline pagination did not advance")
        cursor = next_cursor
        if len(page) < 1000:
            break

    expected = set(range(start_ms, end_ms, DAY_MS))
    missing = sorted(expected - archive_times)
    unresolved = sorted(set(missing) - set(api_rows))
    if unresolved:
        raise RuntimeError(f"official spot REST backfill unresolved {symbol}: {unresolved}")
    ordered = [api_rows[key] for key in missing]
    relative = Path(symbol) / f"kline-backfill-{label}.json"
    target = cache / relative
    write_json(target, ordered)
    return {
        "symbol": symbol,
        "url": KLINE_URL,
        "request_security": "NONE_PUBLIC_MARKET_DATA",
        "policy": "fill_only_timestamps_absent_from_checksum-verified_monthly_archives",
        "pages": pages,
        "requested_start_ms": start_ms,
        "requested_end_exclusive_ms": end_ms,
        "archive_missing_records": len(missing),
        "records": len(ordered),
        "open_times_ms": missing,
        "sha256": sha256_path(target),
        "bytes": target.stat().st_size,
        "cache_relative_path": relative.as_posix(),
    }


def command_fetch(args: argparse.Namespace) -> None:
    cache = Path(args.cache_dir).resolve()
    start_ms, end_ms = month_bounds(args.start_month, args.end_month)
    archives = {}
    backfills = {}
    for symbol in SYMBOLS:
        items = [fetch_archive(cache, symbol, month) for month in month_iter(args.start_month, args.end_month)]
        archives[symbol] = items
        backfills[symbol] = fetch_backfill(
            cache, symbol, start_ms, end_ms, f"{args.start_month}_{args.end_month}", items
        )
    manifest = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "venue": "BINANCE_SPOT",
        "symbols": list(SYMBOLS),
        "interval": "1d",
        "timezone": "UTC",
        "cache_root": str(cache),
        "requested_start_month": args.start_month,
        "requested_end_month": args.end_month,
        "archives": archives,
        "kline_backfills": backfills,
    }
    manifest["content_identity"] = canonical_digest(
        {"symbols": SYMBOLS, "interval": "1d", "archives": archives, "kline_backfills": backfills}
    )
    write_json(Path(args.manifest), manifest)
    print(json.dumps({
        "archives": sum(len(items) for items in archives.values()),
        "backfill_records": sum(item["records"] for item in backfills.values()),
    }))


def load_symbol(cache: Path, archives: list[dict[str, object]], backfill_item: dict[str, object]) -> pd.DataFrame:
    frames = []
    for item in archives:
        path = cache / str(item["cache_relative_path"])
        if sha256_path(path) != item["sha256"]:
            raise RuntimeError(f"archive identity mismatch: {path}")
        frame = pd.read_csv(path, compression="zip", header=None).iloc[:, [0, 1, 2, 3, 4, 5, 7]]
        frame.columns = ["open_ms", "open", "high", "low", "close", "volume", "quote_volume"]
        for column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame["open_ms"] = normalize_open_ms(frame["open_ms"])
        frames.append(frame.dropna())
    path = cache / str(backfill_item["cache_relative_path"])
    if sha256_path(path) != backfill_item["sha256"]:
        raise RuntimeError(f"backfill identity mismatch: {path}")
    backfill = pd.DataFrame(read_json(path))
    if not backfill.empty:
        for column in ["open_ms", "open", "high", "low", "close", "volume", "quote_volume"]:
            backfill[column] = pd.to_numeric(backfill[column], errors="coerce")
        backfill["open_ms"] = normalize_open_ms(backfill["open_ms"])
        frames.append(backfill.dropna())
    combined = pd.concat(frames, ignore_index=True).sort_values("open_ms").drop_duplicates("open_ms")
    combined["open_ms"] = combined["open_ms"].astype("int64")
    return combined.set_index("open_ms", drop=False)


def load_inputs(cache: Path, manifest: dict[str, object]) -> dict[str, pd.DataFrame]:
    if tuple(manifest["symbols"]) != SYMBOLS:
        raise RuntimeError("manifest universe mismatch")
    return {
        symbol: load_symbol(cache, manifest["archives"][symbol], manifest["kline_backfills"][symbol])
        for symbol in SYMBOLS
    }


def block_bootstrap_mean(values: np.ndarray, seed: int, block: int = 30, reps: int = 4000) -> list[float]:
    rng = random.Random(seed)
    count = len(values)
    means = []
    for _ in range(reps):
        sample = []
        while len(sample) < count:
            start = rng.randrange(count)
            sample.extend(values[(start + offset) % count] for offset in range(block))
        means.append(float(np.mean(sample[:count])))
    means.sort()
    return [means[int(reps * 0.025)], means[int(reps * 0.975) - 1]]


def performance(returns: pd.Series, turnover: float, invested: pd.Series, seed: int) -> dict[str, object]:
    equity = (1.0 + returns).cumprod()
    total = float(equity.iloc[-1] - 1.0)
    drawdown = equity / equity.cummax() - 1.0
    annualized = float((1.0 + total) ** (365.0 / len(returns)) - 1.0) if total > -1 else -1.0
    std = returns.std(ddof=1)
    years = pd.to_datetime(returns.index, unit="ms", utc=True).year
    by_year = {}
    for year in sorted(set(years)):
        yearly = returns[years == year]
        by_year[str(year)] = {"days": int(len(yearly)), "return": float((1.0 + yearly).prod() - 1.0)}
    return {
        "days": int(len(returns)),
        "total_return": total,
        "annualized_return": annualized,
        "annualized_volatility": float(std * math.sqrt(365.0)),
        "sharpe_zero_rf": float(returns.mean() / std * math.sqrt(365.0)) if std else None,
        "max_drawdown": float(drawdown.min()),
        "turnover": float(turnover),
        "invested_day_fraction": float(invested.mean()),
        "daily_mean_block_bootstrap_95pct": block_bootstrap_mean(returns.to_numpy(), seed),
        "by_year": by_year,
    }


def data_quality(frames: dict[str, pd.DataFrame], start_ms: int, end_ms: int) -> dict[str, object]:
    expected = (end_ms - start_ms) // DAY_MS
    symbols = {}
    overall = True
    for symbol, frame in frames.items():
        selected = frame[(frame.index >= start_ms) & (frame.index < end_ms)]
        gaps = int((selected.index.to_series().diff().dropna() != DAY_MS).sum())
        invalid = int(
            ((selected[["open", "high", "low", "close"]] <= 0).any(axis=1)
             | (selected["high"] < selected[["open", "close"]].max(axis=1))
             | (selected["low"] > selected[["open", "close"]].min(axis=1))).sum()
        )
        status = "PASS" if len(selected) == expected and gaps == 0 and invalid == 0 else "FAIL"
        overall = overall and status == "PASS"
        symbols[symbol] = {
            "expected_days": int(expected),
            "days": int(len(selected)),
            "gaps": gaps,
            "duplicates": int(selected.index.duplicated().sum()),
            "invalid_ohlc": invalid,
            "status": status,
        }
    return {"status": "PASS" if overall else "FAIL", "symbols": symbols}


def target_weights(frames: dict[str, pd.DataFrame], decision_ms: int, lookback: int) -> dict[str, float]:
    earlier_ms = decision_ms - lookback * DAY_MS
    momentum = {}
    for symbol, frame in frames.items():
        if decision_ms not in frame.index or earlier_ms not in frame.index:
            return {item: 0.0 for item in SYMBOLS}
        value = float(frame.at[decision_ms, "close"] / frame.at[earlier_ms, "close"] - 1.0)
        if value > 0:
            momentum[symbol] = value
    winners = sorted(momentum, key=lambda item: (-momentum[item], item))[:MAX_HOLDINGS]
    weights = {item: 0.0 for item in SYMBOLS}
    if winners:
        for symbol in winners:
            weights[symbol] = 1.0 / len(winners)
    return weights


def simulate_strategy(
    frames: dict[str, pd.DataFrame], start_ms: int, end_ms: int, lookback: int, cost: float, seed: int
) -> dict[str, object]:
    dates = frames[SYMBOLS[0]].index[(frames[SYMBOLS[0]].index >= start_ms) & (frames[SYMBOLS[0]].index < end_ms)]
    cash = 1.0
    quantities = {symbol: 0.0 for symbol in SYMBOLS}
    prior_close_nav = 1.0
    returns = []
    invested_flags = []
    total_turnover = 0.0
    selection_counts = {symbol: 0 for symbol in SYMBOLS}
    selected_quote_volumes = []
    last_month = None
    for day_ms in dates:
        nav_open = cash + sum(quantities[symbol] * float(frames[symbol].at[day_ms, "open"]) for symbol in SYMBOLS)
        month = pd.Timestamp(day_ms, unit="ms", tz="UTC").strftime("%Y-%m")
        if month != last_month:
            decision_ms = int(day_ms - DAY_MS)
            target = target_weights(frames, decision_ms, lookback)
            current = {
                symbol: quantities[symbol] * float(frames[symbol].at[day_ms, "open"]) / nav_open
                for symbol in SYMBOLS
            }
            turnover = sum(abs(target[symbol] - current[symbol]) for symbol in SYMBOLS)
            total_turnover += turnover
            after_cost = nav_open * (1.0 - turnover * cost)
            cash = after_cost * (1.0 - sum(target.values()))
            for symbol in SYMBOLS:
                quantities[symbol] = after_cost * target[symbol] / float(frames[symbol].at[day_ms, "open"])
                if target[symbol] > 0:
                    selection_counts[symbol] += 1
            last_month = month
        nav_close = cash + sum(quantities[symbol] * float(frames[symbol].at[day_ms, "close"]) for symbol in SYMBOLS)
        returns.append(nav_close / prior_close_nav - 1.0)
        active = [symbol for symbol in SYMBOLS if quantities[symbol] > 0]
        invested_flags.append(1.0 if active else 0.0)
        selected_quote_volumes.extend(float(frames[symbol].at[day_ms, "quote_volume"]) for symbol in active)
        prior_close_nav = nav_close
    final_exposure = sum(
        quantities[symbol] * float(frames[symbol].at[int(dates[-1]), "close"]) / prior_close_nav
        for symbol in SYMBOLS
    )
    total_turnover += final_exposure
    after_exit = prior_close_nav * (1.0 - final_exposure * cost)
    returns[-1] = (1.0 + returns[-1]) * (after_exit / prior_close_nav) - 1.0
    series = pd.Series(returns, index=dates, dtype="float64")
    invested = pd.Series(invested_flags, index=dates, dtype="float64")
    result = performance(series, total_turnover, invested, seed)
    result.update({
        "selection_counts": selection_counts,
        "selected_asset_day_quote_volume_min": min(selected_quote_volumes) if selected_quote_volumes else None,
        "selected_asset_day_quote_volume_median": float(np.median(selected_quote_volumes)) if selected_quote_volumes else None,
    })
    return result


def simulate_benchmark(
    frames: dict[str, pd.DataFrame], start_ms: int, end_ms: int, cost: float, seed: int
) -> dict[str, object]:
    dates = frames[SYMBOLS[0]].index[(frames[SYMBOLS[0]].index >= start_ms) & (frames[SYMBOLS[0]].index < end_ms)]
    after_entry = 1.0 * (1.0 - cost)
    quantities = {
        symbol: after_entry / len(SYMBOLS) / float(frames[symbol].at[int(dates[0]), "open"])
        for symbol in SYMBOLS
    }
    prior_nav = 1.0
    values = []
    for day_ms in dates:
        nav = sum(quantities[symbol] * float(frames[symbol].at[day_ms, "close"]) for symbol in SYMBOLS)
        values.append(nav / prior_nav - 1.0)
        prior_nav = nav
    after_exit = prior_nav * (1.0 - cost)
    values[-1] = (1.0 + values[-1]) * (after_exit / prior_nav) - 1.0
    series = pd.Series(values, index=dates, dtype="float64")
    invested = pd.Series(1.0, index=dates, dtype="float64")
    return performance(series, 2.0, invested, seed)


def phase_result(frames: dict[str, pd.DataFrame], phase: str) -> dict[str, object]:
    start_ms, end_ms = (to_ms(value) for value in PHASES[phase])
    quality = data_quality(frames, start_ms, end_ms)
    strategy = {}
    for lookback_offset, lookback in enumerate(LOOKBACKS):
        strategy[str(lookback)] = {
            name: simulate_strategy(
                frames, start_ms, end_ms, lookback, cost, 20260720 + lookback_offset * 10 + cost_offset
            )
            for cost_offset, (name, cost) in enumerate(COSTS.items())
        }
    benchmark = {
        name: simulate_benchmark(frames, start_ms, end_ms, cost, 20261720 + offset)
        for offset, (name, cost) in enumerate(COSTS.items())
    }
    return {
        "phase": phase,
        "period": {"start": PHASES[phase][0], "end_exclusive": PHASES[phase][1]},
        "data_quality": quality,
        "strategy": strategy,
        "equal_weight_buy_and_hold": benchmark,
    }


def command_analyze(args: argparse.Namespace) -> None:
    if args.phase != "development":
        if not args.authorization or not read_json(Path(args.authorization)).get("holdout_authorized"):
            raise RuntimeError("holdout is not authorized")
    manifest = read_json(Path(args.manifest))
    frames = load_inputs(Path(args.cache_dir).resolve(), manifest)
    output = phase_result(frames, args.phase)
    output.update({
        "schema_version": 1,
        "generated_at": utc_now(),
        "manifest_content_identity": manifest["content_identity"],
        "study_code_sha256": sha256_path(Path(__file__)),
        "rules": {
            "symbols": list(SYMBOLS),
            "lookbacks": list(LOOKBACKS),
            "primary_lookback": PRIMARY_LOOKBACK,
            "max_holdings": MAX_HOLDINGS,
            "costs_per_unit_turnover": COSTS,
            "rebalance": "first UTC daily open monthly using prior close information",
        },
    })
    output["content_digest"] = canonical_digest({k: v for k, v in output.items() if k != "generated_at"})
    write_json(Path(args.output), output)
    fixed = output["strategy"][str(PRIMARY_LOOKBACK)]["base"]
    print(json.dumps({"phase": args.phase, "base_total": fixed["total_return"], "max_drawdown": fixed["max_drawdown"]}))


def command_qualify_development(args: argparse.Namespace) -> None:
    development = read_json(Path(args.development))
    fixed = development["strategy"]["90"]
    base = fixed["base"]
    benchmark = development["equal_weight_buy_and_hold"]["base"]
    positive_years = sum(item["return"] > 0 for item in base["by_year"].values())
    passed = (
        development["data_quality"]["status"] == "PASS"
        and base["total_return"] > 0
        and fixed["stress"]["total_return"] > 0
        and positive_years >= 1
        and base["max_drawdown"] >= benchmark["max_drawdown"] + 0.10
        and development["strategy"]["60"]["base"]["total_return"] > 0
        and development["strategy"]["120"]["base"]["total_return"] > 0
        and base["turnover"] <= 50
    )
    output = {
        "generated_at": utc_now(),
        "development_content_digest": development["content_digest"],
        "gate": "pre-registered development gate in checkpoint.json",
        "qualification_status": "PASSED_DEVELOPMENT_GATE" if passed else "FAILED_DEVELOPMENT_GATE_STOP",
        "holdout_authorized": passed,
        "fixed_rule": "MATURE_ALT_SPOT_MONTHLY_TOP2_POSITIVE_90D",
    }
    output["content_digest"] = canonical_digest({k: v for k, v in output.items() if k != "generated_at"})
    write_json(Path(args.output), output)
    print(json.dumps({"status": output["qualification_status"]}))


def command_qualify_evaluation(args: argparse.Namespace) -> None:
    evaluation = read_json(Path(args.evaluation))
    fixed = evaluation["strategy"]["90"]
    base = fixed["base"]
    benchmark = evaluation["equal_weight_buy_and_hold"]["base"]
    positive_years = sum(item["return"] > 0 for item in base["by_year"].values())
    passed = (
        evaluation["data_quality"]["status"] == "PASS"
        and base["total_return"] > 0
        and fixed["stress"]["total_return"] > 0
        and positive_years >= 1
        and base["max_drawdown"] > benchmark["max_drawdown"]
        and evaluation["strategy"]["60"]["base"]["total_return"] > 0
        and evaluation["strategy"]["120"]["base"]["total_return"] > 0
    )
    output = {
        "generated_at": utc_now(),
        "evaluation_content_digest": evaluation["content_digest"],
        "gate": "pre-registered evaluation gate in checkpoint.json",
        "qualification_status": "PASSED_EVALUATION_GATE" if passed else "FAILED_EVALUATION_GATE_STOP",
        "holdout_authorized": passed,
        "fixed_rule": "MATURE_ALT_SPOT_MONTHLY_TOP2_POSITIVE_90D",
    }
    output["content_digest"] = canonical_digest({k: v for k, v in output.items() if k != "generated_at"})
    write_json(Path(args.output), output)
    print(json.dumps({"status": output["qualification_status"]}))


def command_combine(args: argparse.Namespace) -> None:
    development = read_json(Path(args.development))
    evaluation = read_json(Path(args.evaluation))
    confirmation = read_json(Path(args.confirmation))
    evaluation_gate = read_json(Path(args.evaluation_gate))
    fixed = confirmation["strategy"]["90"]
    base = fixed["base"]
    benchmark = confirmation["equal_weight_buy_and_hold"]["base"]
    confirmation_support = (
        confirmation["data_quality"]["status"] == "PASS"
        and base["total_return"] >= 0
        and fixed["stress"]["total_return"] >= 0
        and base["max_drawdown"] > benchmark["max_drawdown"]
        and confirmation["strategy"]["60"]["base"]["total_return"] >= 0
        and confirmation["strategy"]["120"]["base"]["total_return"] >= 0
    )
    evaluation_base = evaluation["strategy"]["90"]["base"]["total_return"]
    if evaluation_gate["holdout_authorized"] and confirmation_support:
        conclusion = "SUPPORTS_WITHIN_SCOPE"
    elif evaluation_base < 0 or base["total_return"] < 0:
        conclusion = "DOES_NOT_SUPPORT"
    else:
        conclusion = "INSUFFICIENT_EVIDENCE"
    output = {
        "generated_at": utc_now(),
        "conclusion": conclusion,
        "scope": "fixed five-symbol Binance spot monthly top-2 positive 90-day momentum",
        "development": development["strategy"]["90"]["base"],
        "evaluation": evaluation["strategy"]["90"]["base"],
        "confirmation": base,
        "confirmation_equal_weight_buy_and_hold": benchmark,
        "confirmation_support_gate": confirmation_support,
        "formal_product_strategy_comparison": "NOT_RUN_NO_COMPARABLE_INSTRUMENT_OR_ACTIVATION_REPLAY",
        "product_effects": "NONE",
    }
    output["content_digest"] = canonical_digest({k: v for k, v in output.items() if k != "generated_at"})
    write_json(Path(args.output), output)
    print(json.dumps({"conclusion": conclusion}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mature-alt spot monthly top-2 momentum study")
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--cache-dir", required=True)
    fetch.add_argument("--start-month", required=True)
    fetch.add_argument("--end-month", required=True)
    fetch.add_argument("--manifest", required=True)
    fetch.set_defaults(func=command_fetch)
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--cache-dir", required=True)
    analyze.add_argument("--manifest", required=True)
    analyze.add_argument("--phase", choices=tuple(PHASES), required=True)
    analyze.add_argument("--authorization")
    analyze.add_argument("--output", required=True)
    analyze.set_defaults(func=command_analyze)
    dev = sub.add_parser("qualify-development")
    dev.add_argument("--development", required=True)
    dev.add_argument("--output", required=True)
    dev.set_defaults(func=command_qualify_development)
    eva = sub.add_parser("qualify-evaluation")
    eva.add_argument("--evaluation", required=True)
    eva.add_argument("--output", required=True)
    eva.set_defaults(func=command_qualify_evaluation)
    combine = sub.add_parser("combine")
    combine.add_argument("--development", required=True)
    combine.add_argument("--evaluation", required=True)
    combine.add_argument("--evaluation-gate", required=True)
    combine.add_argument("--confirmation", required=True)
    combine.add_argument("--output", required=True)
    combine.set_defaults(func=command_combine)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
