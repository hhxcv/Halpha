from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


SYMBOLS = ("AVAXUSDT", "DOTUSDT", "NEARUSDT")
ARCHIVE_ROOT = "https://data.binance.vision/data/futures/um/monthly/klines"
KLINE_URL = "https://fapi.binance.com/fapi/v1/klines"
FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
DAY_MS = 86_400_000
LOOKBACKS = (60, 90, 120)
PRIMARY_LOOKBACK = 90
WEIGHT = 1.0 / 6.0
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
        "symbol": symbol, "month": month, "url": url, "checksum_url": url + ".CHECKSUM",
        "sha256": actual, "bytes": target.stat().st_size, "cache_relative_path": relative.as_posix(),
    }


def fetch_backfill(cache: Path, symbol: str, start_ms: int, end_ms: int, label: str, archives: list[dict[str, object]]) -> dict[str, object]:
    archive_times: set[int] = set()
    for item in archives:
        frame = pd.read_csv(cache / str(item["cache_relative_path"]), compression="zip", header=None, usecols=[0])
        archive_times.update(normalize_open_ms(frame.iloc[:, 0]).dropna().astype("int64").tolist())
    api_rows = {}
    cursor = start_ms
    pages = 0
    while cursor < end_ms:
        query = urllib.parse.urlencode({"symbol": symbol, "interval": "1d", "startTime": cursor, "endTime": end_ms - 1, "limit": 1500})
        page = json.loads(request_bytes(f"{KLINE_URL}?{query}").decode("utf-8"))
        pages += 1
        if not page:
            break
        for row in page:
            open_ms = int(row[0])
            if start_ms <= open_ms < end_ms:
                api_rows[open_ms] = {"open_ms": open_ms, "open": str(row[1]), "high": str(row[2]), "low": str(row[3]), "close": str(row[4]), "volume": str(row[5]), "quote_volume": str(row[7])}
        next_cursor = int(page[-1][0]) + DAY_MS
        if next_cursor <= cursor:
            raise RuntimeError("kline pagination did not advance")
        cursor = next_cursor
        if len(page) < 1500:
            break
    if not archive_times:
        raise RuntimeError(f"no archive Kline rows for {symbol}")
    available_start_ms = min(archive_times)
    missing = sorted(set(range(available_start_ms, end_ms, DAY_MS)) - archive_times)
    unresolved = sorted(set(missing) - set(api_rows))
    if unresolved:
        raise RuntimeError(f"unresolved kline gaps {symbol}: {unresolved}")
    relative = Path(symbol) / f"kline-backfill-{label}.json"
    target = cache / relative
    write_json(target, [api_rows[key] for key in missing])
    return {
        "symbol": symbol, "url": KLINE_URL, "request_security": "NONE_PUBLIC_MARKET_DATA",
        "policy": "fill_only_archive_missing_timestamps_after_first_official_archive_bar",
        "available_start_ms": available_start_ms,
        "requested_prelisting_days": int(max(0, available_start_ms - start_ms) // DAY_MS),
        "pages": pages, "records": len(missing),
        "open_times_ms": missing, "sha256": sha256_path(target), "bytes": target.stat().st_size,
        "cache_relative_path": relative.as_posix(),
    }


def fetch_funding(cache: Path, symbol: str, start_ms: int, end_ms: int, label: str) -> dict[str, object]:
    rows = []
    cursor = start_ms
    pages = 0
    while cursor < end_ms:
        query = urllib.parse.urlencode({"symbol": symbol, "startTime": cursor, "endTime": end_ms - 1, "limit": 1000})
        page = json.loads(request_bytes(f"{FUNDING_URL}?{query}").decode("utf-8"))
        pages += 1
        if not page:
            break
        rows.extend({"fundingTime": int(row["fundingTime"]), "fundingRate": str(row["fundingRate"])} for row in page if start_ms <= int(row["fundingTime"]) < end_ms)
        next_cursor = int(page[-1]["fundingTime"]) + 1
        if next_cursor <= cursor:
            raise RuntimeError("funding pagination did not advance")
        cursor = next_cursor
        if len(page) < 1000:
            break
    unique = {row["fundingTime"]: row for row in rows}
    ordered = [unique[key] for key in sorted(unique)]
    relative = Path(symbol) / f"funding-{label}.json"
    target = cache / relative
    write_json(target, ordered)
    return {
        "symbol": symbol, "url": FUNDING_URL, "request_security": "NONE_PUBLIC_MARKET_DATA",
        "records": len(ordered), "pages": pages, "sha256": sha256_path(target), "bytes": target.stat().st_size,
        "cache_relative_path": relative.as_posix(),
    }


def command_fetch(args: argparse.Namespace) -> None:
    cache = Path(args.cache_dir).resolve()
    start_ms, end_ms = month_bounds(args.start_month, args.end_month)
    archives, backfills, funding = {}, {}, {}
    for symbol in SYMBOLS:
        items = []
        skipped_prelisting_months = []
        for month in month_iter(args.start_month, args.end_month):
            try:
                items.append(fetch_archive(cache, symbol, month))
            except RuntimeError as exc:
                cause = exc.__cause__
                if not items and isinstance(cause, urllib.error.HTTPError) and cause.code == 404:
                    skipped_prelisting_months.append(month)
                    continue
                raise
        archives[symbol] = items
        backfills[symbol] = fetch_backfill(cache, symbol, start_ms, end_ms, f"{args.start_month}_{args.end_month}", items)
        backfills[symbol]["skipped_prelisting_months"] = skipped_prelisting_months
        funding[symbol] = fetch_funding(cache, symbol, start_ms, end_ms, f"{args.start_month}_{args.end_month}")
    manifest = {
        "schema_version": 1, "generated_at": utc_now(), "venue": "BINANCE_USDM", "symbols": list(SYMBOLS),
        "interval": "1d", "timezone": "UTC", "cache_root": str(cache),
        "requested_start_month": args.start_month, "requested_end_month": args.end_month,
        "archives": archives, "kline_backfills": backfills, "funding_snapshots": funding,
    }
    manifest["content_identity"] = canonical_digest({"symbols": SYMBOLS, "archives": archives, "backfills": backfills, "funding": funding})
    write_json(Path(args.manifest), manifest)
    print(json.dumps({"archives": sum(len(items) for items in archives.values()), "backfills": sum(item["records"] for item in backfills.values()), "funding": sum(item["records"] for item in funding.values())}))


def load_inputs(cache: Path, manifest: dict[str, object]) -> tuple[dict[str, pd.DataFrame], dict[str, pd.Series], dict[str, pd.Series]]:
    frames, funding_rates, funding_counts = {}, {}, {}
    for symbol in SYMBOLS:
        parts = []
        for item in manifest["archives"][symbol]:
            path = cache / str(item["cache_relative_path"])
            if sha256_path(path) != item["sha256"]:
                raise RuntimeError(f"archive identity mismatch: {path}")
            frame = pd.read_csv(path, compression="zip", header=None).iloc[:, [0, 1, 2, 3, 4, 5, 7]]
            frame.columns = ["open_ms", "open", "high", "low", "close", "volume", "quote_volume"]
            for column in frame.columns:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
            frame["open_ms"] = normalize_open_ms(frame["open_ms"])
            parts.append(frame.dropna())
        backfill_item = manifest["kline_backfills"][symbol]
        backfill_path = cache / str(backfill_item["cache_relative_path"])
        if sha256_path(backfill_path) != backfill_item["sha256"]:
            raise RuntimeError("backfill identity mismatch")
        backfill = pd.DataFrame(read_json(backfill_path))
        if not backfill.empty:
            for column in ["open_ms", "open", "high", "low", "close", "volume", "quote_volume"]:
                backfill[column] = pd.to_numeric(backfill[column], errors="coerce")
            backfill["open_ms"] = normalize_open_ms(backfill["open_ms"])
            parts.append(backfill.dropna())
        frame = pd.concat(parts, ignore_index=True).sort_values("open_ms").drop_duplicates("open_ms")
        frame["open_ms"] = frame["open_ms"].astype("int64")
        frames[symbol] = frame.set_index("open_ms", drop=False)
        funding_item = manifest["funding_snapshots"][symbol]
        funding_path = cache / str(funding_item["cache_relative_path"])
        if sha256_path(funding_path) != funding_item["sha256"]:
            raise RuntimeError("funding identity mismatch")
        table = pd.DataFrame(read_json(funding_path))
        table["day_ms"] = (table["fundingTime"].astype("int64") // DAY_MS) * DAY_MS
        table["fundingRate"] = table["fundingRate"].astype("float64")
        funding_rates[symbol] = table.groupby("day_ms")["fundingRate"].sum()
        funding_counts[symbol] = table.groupby("day_ms")["fundingRate"].count()
    return frames, funding_rates, funding_counts


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


def performance(returns: pd.Series, turnover: float, adverse: float, seed: int) -> dict[str, object]:
    equity = (1.0 + returns).cumprod()
    total = float(equity.iloc[-1] - 1.0)
    drawdown = equity / equity.cummax() - 1.0
    std = returns.std(ddof=1)
    years = pd.to_datetime(returns.index, unit="ms", utc=True).year
    by_year = {}
    for year in sorted(set(years)):
        yearly = returns[years == year]
        by_year[str(year)] = {"days": int(len(yearly)), "return": float((1.0 + yearly).prod() - 1.0)}
    return {
        "days": int(len(returns)), "total_return": total,
        "annualized_return": float((1.0 + total) ** (365.0 / len(returns)) - 1.0) if total > -1 else -1.0,
        "annualized_volatility": float(std * math.sqrt(365.0)),
        "sharpe_zero_rf": float(returns.mean() / std * math.sqrt(365.0)) if std else None,
        "max_drawdown": float(drawdown.min()), "turnover": float(turnover),
        "worst_daily_intraday_adverse_on_capital": float(adverse),
        "daily_mean_block_bootstrap_95pct": block_bootstrap_mean(returns.to_numpy(), seed), "by_year": by_year,
    }


def data_quality(frames: dict[str, pd.DataFrame], funding_counts: dict[str, pd.Series], start_ms: int, end_ms: int) -> dict[str, object]:
    expected = (end_ms - start_ms) // DAY_MS
    details, overall = {}, True
    for symbol in SYMBOLS:
        selected = frames[symbol][(frames[symbol].index >= start_ms) & (frames[symbol].index < end_ms)]
        gaps = int((selected.index.to_series().diff().dropna() != DAY_MS).sum())
        invalid = int(((selected[["open", "high", "low", "close"]] <= 0).any(axis=1) | (selected["high"] < selected[["open", "close"]].max(axis=1)) | (selected["low"] > selected[["open", "close"]].min(axis=1))).sum())
        counts = funding_counts[symbol].reindex(selected.index, fill_value=0)
        missing_funding_days = int((counts == 0).sum())
        status = "PASS" if len(selected) == expected and gaps == 0 and invalid == 0 and missing_funding_days == 0 else "FAIL"
        overall = overall and status == "PASS"
        details[symbol] = {"expected_days": int(expected), "days": int(len(selected)), "gaps": gaps, "invalid_ohlc": invalid, "missing_funding_days": missing_funding_days, "funding_records": int(counts.sum()), "status": status}
    return {"status": "PASS" if overall else "FAIL", "symbols": details}


def signal_weights(frames: dict[str, pd.DataFrame], decision_ms: int, lookback: int) -> dict[str, float]:
    earlier = decision_ms - lookback * DAY_MS
    weights = {}
    for symbol in SYMBOLS:
        if decision_ms not in frames[symbol].index or earlier not in frames[symbol].index:
            return {item: 0.0 for item in SYMBOLS}
        momentum = float(frames[symbol].at[decision_ms, "close"] / frames[symbol].at[earlier, "close"] - 1.0)
        weights[symbol] = WEIGHT if momentum > 0 else (-WEIGHT if momentum < 0 else 0.0)
    return weights


def simulate(frames: dict[str, pd.DataFrame], funding: dict[str, pd.Series], start_ms: int, end_ms: int, lookback: int, cost: float, seed: int, long_only_benchmark: bool = False) -> dict[str, object]:
    dates = frames[SYMBOLS[0]].index[(frames[SYMBOLS[0]].index >= start_ms) & (frames[SYMBOLS[0]].index < end_ms)]
    nav = 1.0
    quantities = {symbol: 0.0 for symbol in SYMBOLS}
    prev_close = {symbol: None for symbol in SYMBOLS}
    returns, total_turnover, adverse = [], 0.0, 0.0
    last_month = None
    for day_ms in dates:
        nav_before = nav
        nav_open = nav
        for symbol in SYMBOLS:
            if prev_close[symbol] is not None:
                nav_open += quantities[symbol] * (float(frames[symbol].at[day_ms, "open"]) - prev_close[symbol])
        month = pd.Timestamp(day_ms, unit="ms", tz="UTC").strftime("%Y-%m")
        rebalance = (day_ms == dates[0]) if long_only_benchmark else month != last_month
        if rebalance:
            target = ({symbol: WEIGHT for symbol in SYMBOLS} if long_only_benchmark else signal_weights(frames, int(day_ms - DAY_MS), lookback))
            current = {symbol: quantities[symbol] * float(frames[symbol].at[day_ms, "open"]) / nav_open for symbol in SYMBOLS}
            turnover = sum(abs(target[symbol] - current[symbol]) for symbol in SYMBOLS)
            total_turnover += turnover
            nav_open *= 1.0 - turnover * cost
            for symbol in SYMBOLS:
                quantities[symbol] = nav_open * target[symbol] / float(frames[symbol].at[day_ms, "open"])
            last_month = month
        worst_pnl = 0.0
        close_pnl = 0.0
        funding_pnl = 0.0
        for symbol in SYMBOLS:
            row = frames[symbol].loc[day_ms]
            qty = quantities[symbol]
            close_pnl += qty * (float(row["close"]) - float(row["open"]))
            worst_pnl += qty * ((float(row["low"]) if qty >= 0 else float(row["high"])) - float(row["open"]))
            rate = float(funding[symbol].get(day_ms, 0.0))
            funding_pnl -= qty * float(row["close"]) * rate
            prev_close[symbol] = float(row["close"])
        adverse = min(adverse, worst_pnl / nav_open)
        nav = nav_open + close_pnl + funding_pnl
        returns.append(nav / nav_before - 1.0)
        if nav <= 0:
            raise RuntimeError("portfolio equity depleted")
    final_weights = {symbol: quantities[symbol] * prev_close[symbol] / nav for symbol in SYMBOLS}
    exit_turnover = sum(abs(value) for value in final_weights.values())
    total_turnover += exit_turnover
    after_exit = nav * (1.0 - exit_turnover * cost)
    returns[-1] = (1.0 + returns[-1]) * (after_exit / nav) - 1.0
    return performance(pd.Series(returns, index=dates, dtype="float64"), total_turnover, adverse, seed)


def phase_result(frames: dict[str, pd.DataFrame], funding: dict[str, pd.Series], counts: dict[str, pd.Series], phase: str) -> dict[str, object]:
    start_ms, end_ms = (to_ms(value) for value in PHASES[phase])
    strategy = {str(lookback): {name: simulate(frames, funding, start_ms, end_ms, lookback, cost, 20260720 + li * 10 + ci) for ci, (name, cost) in enumerate(COSTS.items())} for li, lookback in enumerate(LOOKBACKS)}
    benchmark = {name: simulate(frames, funding, start_ms, end_ms, PRIMARY_LOOKBACK, cost, 20261720 + ci, long_only_benchmark=True) for ci, (name, cost) in enumerate(COSTS.items())}
    return {"phase": phase, "period": {"start": PHASES[phase][0], "end_exclusive": PHASES[phase][1]}, "data_quality": data_quality(frames, counts, start_ms, end_ms), "strategy": strategy, "continuous_half_long": benchmark}


def command_analyze(args: argparse.Namespace) -> None:
    if args.phase != "development" and (not args.authorization or not read_json(Path(args.authorization)).get("holdout_authorized")):
        raise RuntimeError("holdout is not authorized")
    manifest = read_json(Path(args.manifest))
    frames, funding, counts = load_inputs(Path(args.cache_dir).resolve(), manifest)
    output = phase_result(frames, funding, counts, args.phase)
    output.update({"schema_version": 1, "generated_at": utc_now(), "manifest_content_identity": manifest["content_identity"], "study_code_sha256": sha256_path(Path(__file__)), "rules": {"symbols": list(SYMBOLS), "lookbacks": list(LOOKBACKS), "primary": PRIMARY_LOOKBACK, "weight_per_symbol": WEIGHT, "costs": COSTS}})
    output["content_digest"] = canonical_digest({k: v for k, v in output.items() if k != "generated_at"})
    write_json(Path(args.output), output)
    main = output["strategy"]["90"]["base"]
    print(json.dumps({"phase": args.phase, "base_total": main["total_return"], "max_drawdown": main["max_drawdown"], "adverse": main["worst_daily_intraday_adverse_on_capital"]}))


def command_qualify_development(args: argparse.Namespace) -> None:
    result = read_json(Path(args.development)); fixed = result["strategy"]["90"]; main = fixed["base"]; benchmark = result["continuous_half_long"]["base"]
    passed = result["data_quality"]["status"] == "PASS" and main["total_return"] > 0 and fixed["stress"]["total_return"] > 0 and set(main["by_year"]) == {"2021", "2022"} and all(item["return"] > 0 for item in main["by_year"].values()) and main["max_drawdown"] > -0.35 and main["max_drawdown"] > benchmark["max_drawdown"] and main["worst_daily_intraday_adverse_on_capital"] > -0.20 and result["strategy"]["60"]["base"]["total_return"] > 0 and result["strategy"]["120"]["base"]["total_return"] > 0 and main["turnover"] <= 30
    output = {"generated_at": utc_now(), "development_content_digest": result["content_digest"], "qualification_status": "PASSED_DEVELOPMENT_GATE" if passed else "FAILED_DEVELOPMENT_GATE_STOP", "holdout_authorized": passed, "fixed_rule": "AVAX_DOT_NEAR_MONTHLY_90D_TSMOM_0P5X"}
    output["content_digest"] = canonical_digest({k: v for k, v in output.items() if k != "generated_at"}); write_json(Path(args.output), output); print(json.dumps({"status": output["qualification_status"]}))


def command_qualify_evaluation(args: argparse.Namespace) -> None:
    result = read_json(Path(args.evaluation)); fixed = result["strategy"]["90"]; main = fixed["base"]; benchmark = result["continuous_half_long"]["base"]
    passed = result["data_quality"]["status"] == "PASS" and main["total_return"] > 0 and fixed["stress"]["total_return"] > 0 and set(main["by_year"]) == {"2023", "2024"} and all(item["return"] > 0 for item in main["by_year"].values()) and main["max_drawdown"] > -0.35 and main["max_drawdown"] > benchmark["max_drawdown"] and main["worst_daily_intraday_adverse_on_capital"] > -0.20 and result["strategy"]["60"]["base"]["total_return"] > 0 and result["strategy"]["120"]["base"]["total_return"] > 0
    output = {"generated_at": utc_now(), "evaluation_content_digest": result["content_digest"], "qualification_status": "PASSED_EVALUATION_GATE" if passed else "FAILED_EVALUATION_GATE_STOP", "holdout_authorized": passed, "fixed_rule": "AVAX_DOT_NEAR_MONTHLY_90D_TSMOM_0P5X"}
    output["content_digest"] = canonical_digest({k: v for k, v in output.items() if k != "generated_at"}); write_json(Path(args.output), output); print(json.dumps({"status": output["qualification_status"]}))


def command_combine(args: argparse.Namespace) -> None:
    development = read_json(Path(args.development)); evaluation = read_json(Path(args.evaluation)); gate = read_json(Path(args.evaluation_gate)); confirmation = read_json(Path(args.confirmation)); fixed = confirmation["strategy"]["90"]; main = fixed["base"]; benchmark = confirmation["continuous_half_long"]["base"]
    support = confirmation["data_quality"]["status"] == "PASS" and main["total_return"] > 0 and fixed["stress"]["total_return"] > 0 and main["max_drawdown"] > -0.35 and main["max_drawdown"] > benchmark["max_drawdown"] and main["worst_daily_intraday_adverse_on_capital"] > -0.20 and confirmation["strategy"]["60"]["base"]["total_return"] >= 0 and confirmation["strategy"]["120"]["base"]["total_return"] >= 0
    evaluation_total = evaluation["strategy"]["90"]["base"]["total_return"]
    conclusion = "SUPPORTS_WITHIN_SCOPE" if gate["holdout_authorized"] and support else ("DOES_NOT_SUPPORT" if evaluation_total < 0 or main["total_return"] < 0 else "INSUFFICIENT_EVIDENCE")
    output = {"generated_at": utc_now(), "conclusion": conclusion, "scope": "AVAX/DOT/NEAR monthly 90-day time-series momentum at 0.5x gross with actual funding", "development": development["strategy"]["90"]["base"], "evaluation": evaluation["strategy"]["90"]["base"], "confirmation": main, "confirmation_half_long": benchmark, "confirmation_support_gate": support, "formal_product_strategy_comparison": "NOT_RUN_NO_COMPARABLE_INSTRUMENT_OR_ACTIVATION_REPLAY", "product_effects": "NONE"}
    output["content_digest"] = canonical_digest({k: v for k, v in output.items() if k != "generated_at"}); write_json(Path(args.output), output); print(json.dumps({"conclusion": conclusion}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AVAX/DOT/NEAR monthly perpetual TSMOM study"); sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch"); fetch.add_argument("--cache-dir", required=True); fetch.add_argument("--start-month", required=True); fetch.add_argument("--end-month", required=True); fetch.add_argument("--manifest", required=True); fetch.set_defaults(func=command_fetch)
    analyze = sub.add_parser("analyze"); analyze.add_argument("--cache-dir", required=True); analyze.add_argument("--manifest", required=True); analyze.add_argument("--phase", choices=tuple(PHASES), required=True); analyze.add_argument("--authorization"); analyze.add_argument("--output", required=True); analyze.set_defaults(func=command_analyze)
    dev = sub.add_parser("qualify-development"); dev.add_argument("--development", required=True); dev.add_argument("--output", required=True); dev.set_defaults(func=command_qualify_development)
    eva = sub.add_parser("qualify-evaluation"); eva.add_argument("--evaluation", required=True); eva.add_argument("--output", required=True); eva.set_defaults(func=command_qualify_evaluation)
    combine = sub.add_parser("combine"); combine.add_argument("--development", required=True); combine.add_argument("--evaluation", required=True); combine.add_argument("--evaluation-gate", required=True); combine.add_argument("--confirmation", required=True); combine.add_argument("--output", required=True); combine.set_defaults(func=command_combine)
    return parser


def main() -> None:
    args = build_parser().parse_args(); args.func(args)


if __name__ == "__main__":
    main()
