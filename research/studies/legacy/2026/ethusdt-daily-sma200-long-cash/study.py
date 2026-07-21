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


SYMBOL = "ETHUSDT"
INSTRUMENT = "ETHUSDT-PERP"
ARCHIVE_ROOT = "https://data.binance.vision/data/futures/um/monthly/klines"
FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
DAY_MS = 86_400_000
SMA_DAYS = 200
PHASES = {
    "development": ("2021-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
    "evaluation": ("2024-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
    "confirmation": ("2026-01-01T00:00:00Z", "2026-07-01T00:00:00Z"),
}
COSTS_PER_TRANSITION = {"favorable": 0.0006, "base": 0.0016, "stress": 0.0026}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def to_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def next_month(value: datetime) -> datetime:
    return value.replace(year=value.year + (value.month == 12), month=1 if value.month == 12 else value.month + 1)


def months(start: str, end: str):
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


def command_fetch(args: argparse.Namespace) -> None:
    cache = Path(args.cache_dir).resolve()
    start_ms, end_ms = month_bounds(args.start_month, args.end_month)
    archives = [fetch_archive(cache, month) for month in months(args.start_month, args.end_month)]
    funding = fetch_funding(cache, start_ms, end_ms, f"{args.start_month}_{args.end_month}")
    manifest = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "venue": "BINANCE_USDM",
        "exchange_symbol": SYMBOL,
        "instrument": INSTRUMENT,
        "interval": "1d",
        "timezone": "UTC",
        "cache_root": str(cache),
        "requested_start_month": args.start_month,
        "requested_end_month": args.end_month,
        "archives": archives,
        "funding_snapshot": funding,
        "retrieval_rule": {
            "archive": f"{ARCHIVE_ROOT}/{SYMBOL}/1d/{SYMBOL}-1d-YYYY-MM.zip",
            "archive_integrity": "Verify adjacent official .CHECKSUM",
            "funding": f"GET {FUNDING_URL} with symbol={SYMBOL} and ascending pagination",
        },
    }
    manifest["content_identity"] = canonical_digest(
        {"archives": archives, "funding_snapshot": funding, "symbol": SYMBOL, "interval": "1d"}
    )
    write_json(Path(args.manifest), manifest)
    print(json.dumps({"archives": len(archives), "funding": funding["records"]}))


def load_inputs(cache: Path, manifest: dict[str, object]) -> tuple[pd.DataFrame, pd.Series]:
    frames = []
    for item in manifest["archives"]:
        path = cache / item["cache_relative_path"]
        if sha256_path(path) != item["sha256"]:
            raise RuntimeError(f"archive identity mismatch: {path}")
        frame = pd.read_csv(path, compression="zip", header=None)
        frame = frame.iloc[:, :6]
        frame.columns = ["open_ms", "open", "high", "low", "close", "volume"]
        for column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frames.append(frame.dropna())
    bars = pd.concat(frames, ignore_index=True).sort_values("open_ms").drop_duplicates("open_ms")
    bars["open_ms"] = bars["open_ms"].astype("int64")
    funding_item = manifest["funding_snapshot"]
    funding_path = cache / funding_item["cache_relative_path"]
    if sha256_path(funding_path) != funding_item["sha256"]:
        raise RuntimeError("funding identity mismatch")
    funding = pd.DataFrame(read_json(funding_path))
    if funding.empty:
        return bars, pd.Series(dtype="float64")
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


def performance(returns: pd.Series, positions: pd.Series, transition_count: int, seed: int) -> dict[str, object]:
    equity = (1.0 + returns).cumprod()
    total = float(equity.iloc[-1] - 1.0)
    drawdown = equity / equity.cummax() - 1.0
    days = len(returns)
    annualized = float((1.0 + total) ** (365.0 / days) - 1.0) if total > -1 else -1.0
    volatility = float(returns.std(ddof=1) * math.sqrt(365.0))
    sharpe = float(returns.mean() / returns.std(ddof=1) * math.sqrt(365.0)) if returns.std(ddof=1) else None
    max_drawdown = float(drawdown.min())
    calmar = annualized / abs(max_drawdown) if max_drawdown < 0 else None
    years = pd.to_datetime(returns.index, unit="ms", utc=True).year
    by_year = {}
    for year in sorted(set(years)):
        year_returns = returns[years == year]
        by_year[str(year)] = {
            "days": int(len(year_returns)),
            "return": float((1.0 + year_returns).prod() - 1.0),
        }
    return {
        "days": days,
        "total_return": total,
        "annualized_return": annualized,
        "annualized_volatility": volatility,
        "sharpe_zero_rf": sharpe,
        "max_drawdown": max_drawdown,
        "calmar": calmar,
        "exposure_fraction": float(positions.mean()),
        "transitions_including_stage_boundaries": transition_count,
        "daily_mean_block_bootstrap_95pct": block_bootstrap_mean(returns.to_numpy(), seed=seed),
        "by_year": by_year,
    }


def phase_result(bars: pd.DataFrame, funding: pd.Series, phase: str) -> dict[str, object]:
    bars = bars.copy().set_index("open_ms", drop=False)
    bars["sma200"] = bars["close"].rolling(SMA_DAYS, min_periods=SMA_DAYS).mean()
    bars["signal"] = (bars["close"] > bars["sma200"]).astype("int8")
    bars["position"] = bars["signal"].shift(1).fillna(0).astype("int8")
    start_ms, end_ms = (to_ms(value) for value in PHASES[phase])
    selected = bars[(bars.index >= start_ms) & (bars.index < end_ms)].copy()
    expected = (end_ms - start_ms) // DAY_MS
    gaps = int((selected.index.to_series().diff().dropna() != DAY_MS).sum())
    max_open_gap = float((selected["open"] / selected["close"].shift(1) - 1.0).abs().dropna().max())
    selected["funding_sum"] = funding.reindex(selected.index, fill_value=0.0)
    selected["gross"] = selected["position"] * (selected["close"] / selected["open"] - 1.0)
    selected["funding_pnl"] = -selected["position"] * selected["funding_sum"]
    positions = selected["position"]
    transitions = positions.diff().abs().fillna(positions.iloc[0]).astype("int8")
    transitions.iloc[-1] += positions.iloc[-1]
    transition_count = int(transitions.sum())
    strategy = {}
    benchmark = {}
    for offset, (name, cost) in enumerate(COSTS_PER_TRANSITION.items()):
        returns = selected["gross"] + selected["funding_pnl"] - transitions * cost
        strategy[name] = performance(returns, positions, transition_count, seed=20260720 + offset)
        buy_returns = selected["close"] / selected["open"] - 1.0 - selected["funding_sum"]
        buy_returns = buy_returns.copy()
        buy_returns.iloc[0] -= cost
        buy_returns.iloc[-1] -= cost
        benchmark[name] = performance(
            buy_returns,
            pd.Series(1, index=selected.index, dtype="int8"),
            2,
            seed=20260820 + offset,
        )
    return {
        "phase": phase,
        "period": {"start": PHASES[phase][0], "end_exclusive": PHASES[phase][1]},
        "data_quality": {
            "expected_days": expected,
            "days": int(len(selected)),
            "gaps": gaps,
            "duplicate_days": int(selected.index.duplicated().sum()),
            "invalid_ohlc": int(
                ((selected[["open", "high", "low", "close"]] <= 0).any(axis=1)
                 | (selected["high"] < selected[["open", "close"]].max(axis=1))
                 | (selected["low"] > selected[["open", "close"]].min(axis=1))).sum()
            ),
            "max_abs_open_vs_previous_close_gap": max_open_gap,
            "status": "PASS" if len(selected) == expected and gaps == 0 else "FAIL",
        },
        "strategy": strategy,
        "buy_and_hold": benchmark,
        "cash_total_return": 0.0,
        "funding_rate_sum": float(selected["funding_sum"].sum()),
    }


def command_analyze(args: argparse.Namespace) -> None:
    if args.phase != "development":
        if not args.selection or not read_json(Path(args.selection)).get("holdout_authorized"):
            raise RuntimeError("holdout is not authorized by a passed development gate")
    manifest = read_json(Path(args.manifest))
    bars, funding = load_inputs(Path(args.cache_dir).resolve(), manifest)
    output = phase_result(bars, funding, args.phase)
    output.update(
        {
            "schema_version": 1,
            "generated_at": utc_now(),
            "manifest_content_identity": manifest["content_identity"],
            "study_code_sha256": sha256_path(Path(__file__)),
            "rules": {
                "sma_days": SMA_DAYS,
                "position": "next UTC day long when prior close > prior SMA200, else cash",
                "funding": "actual daily sum applied to 1x initial notional proxy",
                "transition_costs": COSTS_PER_TRANSITION,
            },
        }
    )
    output["content_digest"] = canonical_digest({k: v for k, v in output.items() if k != "generated_at"})
    write_json(Path(args.output), output)
    print(json.dumps({
        "phase": args.phase,
        "strategy_base": output["strategy"]["base"]["total_return"],
        "buy_hold_base": output["buy_and_hold"]["base"]["total_return"],
        "strategy_max_drawdown": output["strategy"]["base"]["max_drawdown"],
    }))


def command_qualify(args: argparse.Namespace) -> None:
    development = read_json(Path(args.development))
    strategy = development["strategy"]["base"]
    benchmark = development["buy_and_hold"]["base"]
    positive_years = sum(item["return"] > 0 for item in strategy["by_year"].values())
    drawdown_ratio = abs(strategy["max_drawdown"]) / abs(benchmark["max_drawdown"])
    passed = (
        strategy["total_return"] > 0
        and positive_years >= 2
        and drawdown_ratio <= 0.80
        and strategy["calmar"] is not None
        and benchmark["calmar"] is not None
        and strategy["calmar"] > benchmark["calmar"]
    )
    output = {
        "generated_at": utc_now(),
        "development_content_digest": development["content_digest"],
        "gate": "positive total; at least two positive years; max-drawdown magnitude <= 80% of buy-and-hold; higher Calmar",
        "positive_years": positive_years,
        "drawdown_ratio_vs_buy_hold": drawdown_ratio,
        "qualification_status": "PASSED_DEVELOPMENT_GATE" if passed else "FAILED_DEVELOPMENT_GATE_STOP",
        "holdout_authorized": passed,
        "fixed_rule": "SMA200_LONG_CASH",
    }
    output["content_digest"] = canonical_digest({k: v for k, v in output.items() if k != "generated_at"})
    write_json(Path(args.output), output)
    print(json.dumps({"status": output["qualification_status"], "drawdown_ratio": drawdown_ratio}))


def command_combine(args: argparse.Namespace) -> None:
    development = read_json(Path(args.development))
    selection = read_json(Path(args.selection))
    evaluation = read_json(Path(args.evaluation))
    confirmation = read_json(Path(args.confirmation))
    eva = evaluation["strategy"]["base"]
    eva_benchmark = evaluation["buy_and_hold"]["base"]
    con = confirmation["strategy"]["base"]
    drawdown_ratio = abs(eva["max_drawdown"]) / abs(eva_benchmark["max_drawdown"])
    evaluation_support = (
        eva["total_return"] > 0
        and set(eva["by_year"]) == {"2024", "2025"}
        and all(item["return"] >= 0 for item in eva["by_year"].values())
        and drawdown_ratio <= 0.85
        and eva["calmar"] is not None
        and eva_benchmark["calmar"] is not None
        and eva["calmar"] > eva_benchmark["calmar"]
    )
    confirmation_support = con["total_return"] > 0
    if evaluation_support and confirmation_support:
        conclusion = "SUPPORTS_WITHIN_SCOPE"
    elif eva["total_return"] < 0:
        conclusion = "DOES_NOT_SUPPORT"
    else:
        conclusion = "INSUFFICIENT_EVIDENCE"
    output = {
        "generated_at": utc_now(),
        "conclusion": conclusion,
        "scope": "ETHUSDT daily SMA200 long/cash, 1x, actual funding proxy and fixed modeled transition costs",
        "development": development["strategy"]["base"],
        "evaluation": eva,
        "confirmation": con,
        "evaluation_buy_and_hold": eva_benchmark,
        "evaluation_drawdown_ratio_vs_buy_hold": drawdown_ratio,
        "evaluation_support_gate": evaluation_support,
        "confirmation_support_gate": confirmation_support,
        "selection_content_digest": selection["content_digest"],
        "formal_product_strategy_comparison": "NOT_RUN_NO_FAIR_EXACT_REPLAY_WITHOUT_SECOND_IMPLEMENTATION",
        "product_effects": "NONE",
    }
    output["content_digest"] = canonical_digest({k: v for k, v in output.items() if k != "generated_at"})
    write_json(Path(args.output), output)
    print(json.dumps({"conclusion": conclusion, "evaluation": eva["total_return"], "confirmation": con["total_return"]}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ETHUSDT daily SMA200 long/cash study")
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
