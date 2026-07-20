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


SYMBOL = "SOLUSDT"
ARCHIVE_ROOT = "https://data.binance.vision/data/futures/um/monthly/klines"
KLINE_URL = "https://fapi.binance.com/fapi/v1/klines"
FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
DAY_MS = 86_400_000
SMA_DAYS = 200
EXPOSURE = 0.5
COSTS_PER_UNIT_TURNOVER = {"favorable": 0.0006, "base": 0.0016, "stress": 0.0026}
PHASES = {
    "development": ("2021-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
    "evaluation": ("2024-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
    "confirmation": ("2026-01-01T00:00:00Z", "2026-07-01T00:00:00Z"),
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


def fetch_archive(cache: Path, month: str) -> dict[str, object]:
    filename = f"{SYMBOL}-1d-{month}.zip"
    url = f"{ARCHIVE_ROOT}/{SYMBOL}/1d/{filename}"
    expected = request_bytes(url + ".CHECKSUM").decode("utf-8").split()[0].lower()
    relative = Path("klines-1d") / filename
    target = cache / relative
    if not target.exists() or sha256_path(target) != expected:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(request_bytes(url))
    actual = sha256_path(target)
    if actual != expected:
        raise RuntimeError(f"checksum mismatch for {month}")
    return {
        "month": month,
        "url": url,
        "checksum_url": url + ".CHECKSUM",
        "sha256": actual,
        "bytes": target.stat().st_size,
        "cache_relative_path": relative.as_posix(),
    }


def fetch_funding(cache: Path, start_ms: int, end_ms: int, label: str) -> dict[str, object]:
    rows = []
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
        rows.extend(
            {"fundingTime": int(row["fundingTime"]), "fundingRate": str(row["fundingRate"])}
            for row in page
            if start_ms <= int(row["fundingTime"]) < end_ms
        )
        next_cursor = int(page[-1]["fundingTime"]) + 1
        if next_cursor <= cursor:
            raise RuntimeError("funding pagination did not advance")
        cursor = next_cursor
        if len(page) < 1000:
            break
    unique = {row["fundingTime"]: row for row in rows}
    ordered = [unique[key] for key in sorted(unique)]
    relative = Path(f"funding-{label}.json")
    target = cache / relative
    write_json(target, ordered)
    return {
        "url": FUNDING_URL,
        "request_security": "NONE_PUBLIC_MARKET_DATA",
        "records": len(ordered),
        "pages": pages,
        "requested_start_ms": start_ms,
        "requested_end_exclusive_ms": end_ms,
        "sha256": sha256_path(target),
        "bytes": target.stat().st_size,
        "cache_relative_path": relative.as_posix(),
    }


def normalize_open_ms(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    return numeric.where(numeric < 100_000_000_000_000, numeric // 1000)


def fetch_kline_backfill(
    cache: Path,
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
            {"symbol": SYMBOL, "interval": "1d", "startTime": cursor, "endTime": end_ms - 1, "limit": 1500}
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
                }
        next_cursor = int(page[-1][0]) + DAY_MS
        if next_cursor <= cursor:
            raise RuntimeError("kline pagination did not advance")
        cursor = next_cursor
        if len(page) < 1500:
            break

    expected_times = set(range(start_ms, end_ms, DAY_MS))
    missing_before = sorted(expected_times - archive_times)
    unresolved = sorted(set(missing_before) - set(api_rows))
    if unresolved:
        raise RuntimeError(f"official REST kline backfill unresolved timestamps: {unresolved}")
    ordered = [api_rows[key] for key in missing_before]
    relative = Path(f"kline-backfill-{label}.json")
    target = cache / relative
    write_json(target, ordered)
    return {
        "url": KLINE_URL,
        "request_security": "NONE_PUBLIC_MARKET_DATA",
        "policy": "fill_only_timestamps_absent_from_checksum-verified_monthly_archives",
        "requested_start_ms": start_ms,
        "requested_end_exclusive_ms": end_ms,
        "pages": pages,
        "archive_missing_records": len(missing_before),
        "records": len(ordered),
        "open_times_ms": missing_before,
        "sha256": sha256_path(target),
        "bytes": target.stat().st_size,
        "cache_relative_path": relative.as_posix(),
    }


def command_fetch(args: argparse.Namespace) -> None:
    cache = Path(args.cache_dir).resolve()
    start_ms, end_ms = month_bounds(args.start_month, args.end_month)
    archives = [fetch_archive(cache, month) for month in month_iter(args.start_month, args.end_month)]
    kline_backfill = fetch_kline_backfill(
        cache, start_ms, end_ms, f"{args.start_month}_{args.end_month}", archives
    )
    funding = fetch_funding(cache, start_ms, end_ms, f"{args.start_month}_{args.end_month}")
    manifest = {
        "schema_version": 2,
        "generated_at": utc_now(),
        "venue": "BINANCE_USDM",
        "symbol": SYMBOL,
        "instrument": "SOLUSDT-PERP",
        "interval": "1d",
        "timezone": "UTC",
        "cache_root": str(cache),
        "requested_start_month": args.start_month,
        "requested_end_month": args.end_month,
        "archives": archives,
        "kline_backfill": kline_backfill,
        "funding_snapshot": funding,
    }
    manifest["content_identity"] = canonical_digest(
        {
            "archives": archives,
            "kline_backfill": kline_backfill,
            "funding_snapshot": funding,
            "symbol": SYMBOL,
            "interval": "1d",
        }
    )
    write_json(Path(args.manifest), manifest)
    print(json.dumps({
        "archives": len(archives),
        "kline_backfill": kline_backfill["records"],
        "funding": funding["records"],
    }))


def load_inputs(cache: Path, manifest: dict[str, object]) -> tuple[pd.DataFrame, pd.Series]:
    frames = []
    for item in manifest["archives"]:
        path = cache / item["cache_relative_path"]
        if sha256_path(path) != item["sha256"]:
            raise RuntimeError(f"archive identity mismatch: {path}")
        frame = pd.read_csv(path, compression="zip", header=None).iloc[:, :6]
        frame.columns = ["open_ms", "open", "high", "low", "close", "volume"]
        for column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame["open_ms"] = normalize_open_ms(frame["open_ms"])
        frames.append(frame.dropna())
    backfill_item = manifest.get("kline_backfill")
    if backfill_item:
        backfill_path = cache / backfill_item["cache_relative_path"]
        if sha256_path(backfill_path) != backfill_item["sha256"]:
            raise RuntimeError("kline backfill identity mismatch")
        backfill = pd.DataFrame(read_json(backfill_path))
        if not backfill.empty:
            for column in ["open_ms", "open", "high", "low", "close", "volume"]:
                backfill[column] = pd.to_numeric(backfill[column], errors="coerce")
            backfill["open_ms"] = normalize_open_ms(backfill["open_ms"])
            frames.append(backfill.dropna())
    bars = pd.concat(frames, ignore_index=True).sort_values("open_ms").drop_duplicates("open_ms")
    bars["open_ms"] = bars["open_ms"].astype("int64")
    funding_item = manifest["funding_snapshot"]
    funding_path = cache / funding_item["cache_relative_path"]
    if sha256_path(funding_path) != funding_item["sha256"]:
        raise RuntimeError("funding identity mismatch")
    funding = pd.DataFrame(read_json(funding_path))
    funding["day_ms"] = (funding["fundingTime"].astype("int64") // DAY_MS) * DAY_MS
    funding["fundingRate"] = funding["fundingRate"].astype("float64")
    return bars, funding.groupby("day_ms")["fundingRate"].sum()


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


def max_episode_adverse(selected: pd.DataFrame) -> float:
    current_position = 0.0
    entry = 0.0
    worst = 0.0
    for row in selected.itertuples():
        position = float(row.position)
        if position != current_position:
            current_position = position
            entry = float(row.open)
        if position > 0:
            adverse = position * (float(row.low) / entry - 1.0)
        elif position < 0:
            adverse = abs(position) * (1.0 - float(row.high) / entry)
        else:
            adverse = 0.0
        worst = min(worst, adverse)
    return worst


def performance(returns: pd.Series, positions: pd.Series, turnover: pd.Series, adverse: float, seed: int) -> dict[str, object]:
    equity = (1.0 + returns).cumprod()
    total = float(equity.iloc[-1] - 1.0)
    drawdown = equity / equity.cummax() - 1.0
    annualized = float((1.0 + total) ** (365.0 / len(returns)) - 1.0) if total > -1 else -1.0
    volatility = float(returns.std(ddof=1) * math.sqrt(365.0))
    sharpe = float(returns.mean() / returns.std(ddof=1) * math.sqrt(365.0)) if returns.std(ddof=1) else None
    years = pd.to_datetime(returns.index, unit="ms", utc=True).year
    by_year = {}
    for year in sorted(set(years)):
        yearly = returns[years == year]
        by_year[str(year)] = {"days": int(len(yearly)), "return": float((1.0 + yearly).prod() - 1.0)}
    return {
        "days": len(returns),
        "total_return": total,
        "annualized_return": annualized,
        "annualized_volatility": volatility,
        "sharpe_zero_rf": sharpe,
        "max_drawdown": float(drawdown.min()),
        "exposure_mean_abs": float(positions.abs().mean()),
        "long_fraction": float((positions > 0).mean()),
        "short_fraction": float((positions < 0).mean()),
        "turnover": float(turnover.sum()),
        "max_episode_adverse_on_capital": adverse,
        "daily_mean_block_bootstrap_95pct": block_bootstrap_mean(returns.to_numpy(), seed=seed),
        "by_year": by_year,
    }


def phase_result(bars: pd.DataFrame, funding: pd.Series, phase: str) -> dict[str, object]:
    bars = bars.copy().set_index("open_ms", drop=False)
    bars["sma200"] = bars["close"].rolling(SMA_DAYS, min_periods=SMA_DAYS).mean()
    bars["signal"] = np.where(bars["sma200"].isna(), 0.0, np.where(bars["close"] > bars["sma200"], EXPOSURE, -EXPOSURE))
    bars["position"] = bars["signal"].shift(1).fillna(0.0)
    start_ms, end_ms = (to_ms(value) for value in PHASES[phase])
    selected = bars[(bars.index >= start_ms) & (bars.index < end_ms)].copy()
    expected = (end_ms - start_ms) // DAY_MS
    gaps = int((selected.index.to_series().diff().dropna() != DAY_MS).sum())
    selected["funding_sum"] = funding.reindex(selected.index, fill_value=0.0)
    selected["price_return"] = selected["close"] / selected["open"] - 1.0
    positions = selected["position"]
    turnover = positions.diff().abs().fillna(positions.abs())
    turnover.iloc[-1] += abs(positions.iloc[-1])
    adverse = max_episode_adverse(selected)
    strategy = {}
    benchmark = {}
    for offset, (name, cost) in enumerate(COSTS_PER_UNIT_TURNOVER.items()):
        returns = positions * selected["price_return"] - positions * selected["funding_sum"] - turnover * cost
        strategy[name] = performance(returns, positions, turnover, adverse, seed=20260720 + offset)
        benchmark_positions = pd.Series(EXPOSURE, index=selected.index)
        benchmark_turnover = pd.Series(0.0, index=selected.index)
        benchmark_turnover.iloc[0] = EXPOSURE
        benchmark_turnover.iloc[-1] += EXPOSURE
        benchmark_returns = (
            benchmark_positions * selected["price_return"]
            - benchmark_positions * selected["funding_sum"]
            - benchmark_turnover * cost
        )
        benchmark_adverse = float((EXPOSURE * (selected["low"] / selected["open"].iloc[0] - 1.0)).min())
        benchmark[name] = performance(
            benchmark_returns,
            benchmark_positions,
            benchmark_turnover,
            benchmark_adverse,
            seed=20260820 + offset,
        )
    return {
        "phase": phase,
        "period": {"start": PHASES[phase][0], "end_exclusive": PHASES[phase][1]},
        "data_quality": {
            "expected_days": expected,
            "days": int(len(selected)),
            "gaps": gaps,
            "duplicates": int(selected.index.duplicated().sum()),
            "invalid_ohlc": int(
                ((selected[["open", "high", "low", "close"]] <= 0).any(axis=1)
                 | (selected["high"] < selected[["open", "close"]].max(axis=1))
                 | (selected["low"] > selected[["open", "close"]].min(axis=1))).sum()
            ),
            "status": "PASS" if len(selected) == expected and gaps == 0 else "FAIL",
        },
        "strategy": strategy,
        "continuous_half_long": benchmark,
        "funding_rate_sum": float(selected["funding_sum"].sum()),
    }


def command_analyze(args: argparse.Namespace) -> None:
    if args.phase != "development":
        if not args.selection or not read_json(Path(args.selection)).get("holdout_authorized"):
            raise RuntimeError("holdout is not authorized")
    manifest = read_json(Path(args.manifest))
    bars, funding = load_inputs(Path(args.cache_dir).resolve(), manifest)
    output = phase_result(bars, funding, args.phase)
    output.update({
        "schema_version": 1,
        "generated_at": utc_now(),
        "manifest_content_identity": manifest["content_identity"],
        "study_code_sha256": sha256_path(Path(__file__)),
        "rules": {
            "sma_days": SMA_DAYS,
            "exposure": EXPOSURE,
            "positions": "next UTC day +0.5 long above prior SMA200, else -0.5 short",
            "turnover_costs": COSTS_PER_UNIT_TURNOVER,
        },
    })
    output["content_digest"] = canonical_digest({k: v for k, v in output.items() if k != "generated_at"})
    write_json(Path(args.output), output)
    print(json.dumps({
        "phase": args.phase,
        "strategy_base": output["strategy"]["base"]["total_return"],
        "benchmark_base": output["continuous_half_long"]["base"]["total_return"],
        "adverse": output["strategy"]["base"]["max_episode_adverse_on_capital"],
    }))


def command_qualify(args: argparse.Namespace) -> None:
    development = read_json(Path(args.development))
    strategy = development["strategy"]["base"]
    benchmark = development["continuous_half_long"]["base"]
    ci_low = strategy["daily_mean_block_bootstrap_95pct"][0]
    passed = (
        development["data_quality"]["status"] == "PASS"
        and
        strategy["total_return"] > 0
        and set(strategy["by_year"]) == {"2021", "2022", "2023"}
        and all(item["return"] > 0 for item in strategy["by_year"].values())
        and ci_low > 0
        and strategy["max_drawdown"] > benchmark["max_drawdown"]
        and strategy["max_episode_adverse_on_capital"] > -0.50
    )
    output = {
        "generated_at": utc_now(),
        "development_content_digest": development["content_digest"],
        "gate": "positive total and every development year; 30-day block-bootstrap lower daily mean >0; lower drawdown than half-long; episode adverse > -50%",
        "data_quality_status": development["data_quality"]["status"],
        "qualification_status": "PASSED_DEVELOPMENT_GATE" if passed else "FAILED_DEVELOPMENT_GATE_STOP",
        "holdout_authorized": passed,
        "fixed_rule": "SOLUSDT_DAILY_SMA200_LONG_SHORT_0P5X",
    }
    output["content_digest"] = canonical_digest({k: v for k, v in output.items() if k != "generated_at"})
    write_json(Path(args.output), output)
    print(json.dumps({"status": output["qualification_status"], "ci_low": ci_low}))


def command_combine(args: argparse.Namespace) -> None:
    development = read_json(Path(args.development))
    selection = read_json(Path(args.selection))
    evaluation = read_json(Path(args.evaluation))
    confirmation = read_json(Path(args.confirmation))
    eva = evaluation["strategy"]["base"]
    eva_benchmark = evaluation["continuous_half_long"]["base"]
    con = confirmation["strategy"]["base"]
    evaluation_support = (
        eva["total_return"] > 0
        and set(eva["by_year"]) == {"2024", "2025"}
        and all(item["return"] > 0 for item in eva["by_year"].values())
        and eva["daily_mean_block_bootstrap_95pct"][0] > 0
        and eva["max_drawdown"] > eva_benchmark["max_drawdown"]
        and eva["max_episode_adverse_on_capital"] > -0.50
    )
    confirmation_support = con["total_return"] > 0 and con["max_episode_adverse_on_capital"] > -0.50
    if evaluation_support and confirmation_support:
        conclusion = "SUPPORTS_WITHIN_SCOPE"
    elif eva["total_return"] < 0:
        conclusion = "DOES_NOT_SUPPORT"
    else:
        conclusion = "INSUFFICIENT_EVIDENCE"
    output = {
        "generated_at": utc_now(),
        "conclusion": conclusion,
        "scope": "SOLUSDT daily SMA200 0.5x long/short with actual funding proxy and fixed turnover costs",
        "development": development["strategy"]["base"],
        "evaluation": eva,
        "confirmation": con,
        "evaluation_half_long": eva_benchmark,
        "evaluation_support_gate": evaluation_support,
        "confirmation_support_gate": confirmation_support,
        "selection_content_digest": selection["content_digest"],
        "formal_product_strategy_comparison": "NOT_RUN_NO_COMPARABLE_INSTRUMENT_OR_ACTIVATION_REPLAY",
        "product_effects": "NONE",
    }
    output["content_digest"] = canonical_digest({k: v for k, v in output.items() if k != "generated_at"})
    write_json(Path(args.output), output)
    print(json.dumps({"conclusion": conclusion, "evaluation": eva["total_return"], "confirmation": con["total_return"]}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SOLUSDT daily SMA200 0.5x long/short study")
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
    analyze.add_argument("--selection")
    analyze.add_argument("--output", required=True)
    analyze.set_defaults(func=command_analyze)
    qualify = sub.add_parser("qualify")
    qualify.add_argument("--development", required=True)
    qualify.add_argument("--output", required=True)
    qualify.set_defaults(func=command_qualify)
    combine = sub.add_parser("combine")
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
