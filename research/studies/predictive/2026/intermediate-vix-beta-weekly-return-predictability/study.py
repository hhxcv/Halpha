from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import scipy
from scipy.stats import spearmanr
import statsmodels
import statsmodels.api as sm


HERE = Path(__file__).resolve().parent
CACHE_ROOT = Path(
    "D:/projects/Codex/CodexHome/research-data/halpha/"
    "intermediate-vix-beta-weekly-return-predictability/2026-07-22-v1"
)
BASELINE_COMMIT = "0bdfeffa616260cebd2d2188ddc8deb9e85c77f4"
SYMBOLS = [
    "1000XECUSDT", "AAVEUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT",
    "CRVUSDT", "DASHUSDT", "ENSUSDT", "ETCUSDT", "HBARUSDT",
    "KAVAUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "RUNEUSDT",
    "SNXUSDT", "SOLUSDT", "TRXUSDT", "UNIUSDT", "VETUSDT",
    "XLMUSDT", "XMRUSDT", "XRPUSDT", "ZECUSDT", "ZILUSDT",
]
DATA_START = "2022-01-01T00:00:00Z"
DATA_END_EXCLUSIVE = "2026-07-22T00:00:00Z"
STAGES = {
    "development": ("2023-03-04T00:00:00Z", "2024-03-02T00:00:00Z"),
    "evaluation": ("2024-03-02T00:00:00Z", "2025-03-01T00:00:00Z"),
    "confirmation": ("2025-03-01T00:00:00Z", "2026-07-18T00:00:00Z"),
}
EXPECTED_WEEKS = {
    name: len(pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="7D", inclusive="left"))
    for name, (start, end) in STAGES.items()
}
WINDOWS = {"primary_36w": 36, "diagnostic_26w": 26, "diagnostic_52w": 52}
CONFIG = {
    "predictor_id": "RESEARCH_INTERMEDIATE_VIX_BETA_36W_NEXT_WEEK_V1",
    "minimum_median_quote_volume_30d": 10_000_000.0,
    "minimum_rankable": 20,
    "tail_fraction": 0.20,
    "vix_ar_minimum_weeks": 52,
    "vix_ar_start": "2019-01-05T00:00:00Z",
    "action_gap_days": 2,
    "target_days": 7,
    "stress_round_trip_underlying": 0.0052,
    "economic_notional_fraction": 0.25,
    "annual_full_plan_hurdle": 0.04,
    "bootstrap": {"block_weeks": 4, "repetitions": 5000, "seed": 20260722},
    "hac_maxlags": 4,
    "minimum_positive_spread_fraction": 0.55,
    "minimum_selected_symbols": 10,
    "minimum_positive_symbol_fraction": 0.50,
    "maximum_positive_contribution_share": 0.40,
    "maximum_abs_score_control_correlation": 0.90,
}
VIX_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
BINANCE_BASE = "https://fapi.binance.com"


def now_utc() -> str:
    return pd.Timestamp.now(tz="UTC").isoformat()


def digest_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def digest_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def digest_value(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    payload = dict(value)
    payload["content_digest"] = digest_value(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def fetch_bytes(url: str, attempts: int = 4) -> bytes:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Halpha-research/1.0"})
            with urllib.request.urlopen(request, timeout=40) as response:
                return response.read()
        except Exception as exc:
            last = exc
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed after {attempts} attempts: {url}: {last}")


def store_raw(relative: Path, raw: bytes) -> dict[str, Any]:
    path = CACHE_ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {"path": str(path), "bytes": len(raw), "sha256": digest_bytes(raw)}


def command_checkpoint(_args: argparse.Namespace) -> None:
    frozen = {name: digest_file(HERE / name) for name in ["README.md", "sources.md", "preregistration.md", "study.py"]}
    payload = {
        "created_at_utc": now_utc(),
        "baseline_commit": BASELINE_COMMIT,
        "formal_strategy": {"id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT", "version": "1.0.1", "instrument": "BTCUSDT-PERP"},
        "research_kind": "PREDICTIVE",
        "question": "Does intermediate market-controlled VIX-innovation beta predict next-week mature-perpetual returns at strategy-worthy magnitude?",
        "replication_status": "Operational post-publication adaptation of Han 2024; not a numerical replication.",
        "evidence_boundary": "All stages start after the paper sample, but broad crypto paths were exposed in earlier Halpha work.",
        "symbols": SYMBOLS,
        "data_start": DATA_START,
        "data_end_exclusive": DATA_END_EXCLUSIVE,
        "stages": STAGES,
        "expected_weeks": EXPECTED_WEEKS,
        "windows": WINDOWS,
        "config": CONFIG,
        "sources": {"cboe_vix": VIX_URL, "binance_base": BINANCE_BASE},
        "frozen_file_sha256": frozen,
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
            "statsmodels": statsmodels.__version__,
        },
        "cache_root": str(CACHE_ROOT),
        "stage_open_rule": "development -> evaluation on PASS -> confirmation on PASS",
    }
    write_json(HERE / "checkpoint.json", payload)
    print(json.dumps({"digest": read_json(HERE / "checkpoint.json")["content_digest"], "expected_weeks": EXPECTED_WEEKS}))


def assert_checkpoint() -> None:
    checkpoint = read_json(HERE / "checkpoint.json")
    checks = {
        name: checkpoint["frozen_file_sha256"][name] == digest_file(HERE / name)
        for name in checkpoint["frozen_file_sha256"]
    }
    if not all(checks.values()):
        raise RuntimeError(f"frozen identity mismatch: {checks}")


def command_fetch(_args: argparse.Namespace) -> None:
    assert_checkpoint()
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    vix_raw = fetch_bytes(VIX_URL)
    vix_item = {"url": VIX_URL, **store_raw(Path("cboe") / "VIX_History.csv", vix_raw)}
    exchange_url = f"{BINANCE_BASE}/fapi/v1/exchangeInfo"
    exchange_raw = fetch_bytes(exchange_url)
    exchange_item = {"url": exchange_url, **store_raw(Path("binance") / "exchangeInfo.json", exchange_raw)}
    start_ms = int(pd.Timestamp(DATA_START).timestamp() * 1000)
    end_ms = int(pd.Timestamp(DATA_END_EXCLUSIVE).timestamp() * 1000) - 1
    pages: list[dict[str, Any]] = []
    for symbol in SYMBOLS:
        cursor = start_ms
        page = 0
        while cursor <= end_ms:
            query = urllib.parse.urlencode({
                "symbol": symbol, "interval": "1d", "startTime": cursor,
                "endTime": end_ms, "limit": 1500,
            })
            url = f"{BINANCE_BASE}/fapi/v1/klines?{query}"
            raw = fetch_bytes(url)
            rows = json.loads(raw)
            if not rows:
                break
            item = {
                "symbol": symbol, "page": page, "url": url,
                **store_raw(Path("binance") / "klines" / symbol / f"page-{page:03d}.json", raw),
            }
            pages.append(item)
            next_cursor = int(rows[-1][0]) + 86_400_000
            if next_cursor <= cursor:
                raise RuntimeError(f"pagination did not advance: {symbol}")
            cursor = next_cursor
            page += 1
            if len(rows) < 1500:
                break
            time.sleep(0.05)
    payload = {
        "fetched_at_utc": now_utc(),
        "data_start": DATA_START,
        "data_end_exclusive": DATA_END_EXCLUSIVE,
        "vix": vix_item,
        "exchange_info": exchange_item,
        "kline_pages": pages,
    }
    write_json(HERE / "source_manifest.json", payload)
    print(json.dumps({"kline_pages": len(pages), "symbols": len(set(item["symbol"] for item in pages)), "digest": read_json(HERE / "source_manifest.json")["content_digest"]}))


def verified_bytes(item: dict[str, Any]) -> bytes:
    raw = Path(item["path"]).read_bytes()
    if len(raw) != item["bytes"] or digest_bytes(raw) != item["sha256"]:
        raise RuntimeError(f"source identity mismatch: {item['path']}")
    return raw


def load_data() -> tuple[dict[str, pd.DataFrame], pd.DataFrame, dict[str, Any]]:
    manifest = read_json(HERE / "source_manifest.json")
    by_symbol: dict[str, list[Any]] = {symbol: [] for symbol in SYMBOLS}
    for item in manifest["kline_pages"]:
        by_symbol[item["symbol"]].extend(json.loads(verified_bytes(item)))
    bars: dict[str, pd.DataFrame] = {}
    columns = [
        "open_time", "open", "high", "low", "close", "volume", "close_time",
        "quote_volume", "trades", "taker_base", "taker_quote", "ignore",
    ]
    for symbol, rows in by_symbol.items():
        frame = pd.DataFrame(rows, columns=columns)
        frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
        for column in ["open", "high", "low", "close", "volume", "quote_volume"]:
            frame[column] = pd.to_numeric(frame[column], errors="raise")
        bars[symbol] = frame.drop_duplicates("open_time", keep="last").sort_values("open_time").set_index("open_time")
    vix_raw = verified_bytes(manifest["vix"])
    from io import BytesIO
    vix = pd.read_csv(BytesIO(vix_raw))
    vix.columns = [str(column).strip().upper() for column in vix.columns]
    date_column = "DATE" if "DATE" in vix.columns else vix.columns[0]
    close_column = "CLOSE" if "CLOSE" in vix.columns else vix.columns[-1]
    vix[date_column] = pd.to_datetime(vix[date_column], utc=True)
    vix[close_column] = pd.to_numeric(vix[close_column], errors="coerce")
    vix = vix[[date_column, close_column]].dropna().drop_duplicates(date_column, keep="last").set_index(date_column).sort_index()
    vix.columns = ["close"]
    exchange = json.loads(verified_bytes(manifest["exchange_info"]))
    return bars, vix, exchange


def command_inspect(_args: argparse.Namespace) -> None:
    assert_checkpoint()
    bars, vix, exchange = load_data()
    expected = pd.date_range(pd.Timestamp(DATA_START), pd.Timestamp(DATA_END_EXCLUSIVE), freq="1D", inclusive="left")
    symbol_checks: dict[str, Any] = {}
    status = True
    for symbol, frame in bars.items():
        selected = frame[(frame.index >= expected[0]) & (frame.index < pd.Timestamp(DATA_END_EXCLUSIVE))]
        missing = expected.difference(selected.index)
        invalid = int(((selected[["open", "high", "low", "close"]] <= 0).any(axis=1)).sum())
        bad_range = int(((selected["high"] < selected[["open", "close"]].max(axis=1)) | (selected["low"] > selected[["open", "close"]].min(axis=1))).sum())
        check = {
            "rows": int(len(selected)), "first": selected.index.min().isoformat(), "last": selected.index.max().isoformat(),
            "missing": int(len(missing)), "duplicates": int(selected.index.duplicated().sum()),
            "invalid_ohlc": invalid, "invalid_range": bad_range,
            "median_quote_volume": float(selected["quote_volume"].median()),
        }
        symbol_checks[symbol] = check
        status = status and check["missing"] == 0 and check["duplicates"] == 0 and invalid == 0 and bad_range == 0
    current = {item["symbol"]: item for item in exchange["symbols"] if item["symbol"] in SYMBOLS}
    current_ok = len(current) == len(SYMBOLS) and all(item["status"] == "TRADING" and item["contractType"] == "PERPETUAL" for item in current.values())
    vix_selected = vix[(vix.index >= pd.Timestamp("2019-01-01", tz="UTC")) & (vix.index < pd.Timestamp(DATA_END_EXCLUSIVE))]
    vix_ok = len(vix_selected) >= 1800 and bool((vix_selected["close"] > 0).all()) and not vix_selected.index.duplicated().any()
    payload = {
        "checked_at_utc": now_utc(),
        "status": "PASS" if status and current_ok and vix_ok else "FAIL",
        "symbols": symbol_checks,
        "current_exchange": {"present": len(current), "all_trading_perpetual": current_ok},
        "vix": {
            "rows_since_2019": int(len(vix_selected)), "first": vix_selected.index.min().isoformat(),
            "last": vix_selected.index.max().isoformat(), "positive": bool((vix_selected["close"] > 0).all()),
            "duplicates": int(vix_selected.index.duplicated().sum()),
        },
        "source_manifest_digest": read_json(HERE / "source_manifest.json")["content_digest"],
    }
    write_json(HERE / "data_quality.json", payload)
    print(json.dumps({"status": payload["status"], "symbols": len(symbol_checks), "vix_rows": len(vix_selected)}))
    if payload["status"] != "PASS":
        raise RuntimeError("data quality failed")


def weekly_vix_innovations(vix: pd.DataFrame) -> pd.Series:
    saturdays = pd.date_range(pd.Timestamp(CONFIG["vix_ar_start"]), pd.Timestamp(DATA_END_EXCLUSIVE), freq="7D", inclusive="left")
    values: list[float] = []
    for saturday in saturdays:
        friday = saturday - pd.Timedelta(days=1)
        eligible = vix[(vix.index <= friday) & (vix.index >= friday - pd.Timedelta(days=2))]
        values.append(float(eligible["close"].iloc[-1]) if not eligible.empty else math.nan)
    weekly_close = pd.Series(values, index=saturdays, dtype=float)
    changes = weekly_close.diff()
    innovations = pd.Series(index=saturdays, dtype=float)
    minimum = int(CONFIG["vix_ar_minimum_weeks"])
    for index in range(len(changes)):
        if index < minimum + 1 or not math.isfinite(changes.iloc[index]):
            continue
        history = changes.iloc[1:index].dropna()
        if len(history) < minimum:
            continue
        y = history.iloc[1:].to_numpy(float)
        x = sm.add_constant(history.iloc[:-1].to_numpy(float))
        fitted = np.linalg.lstsq(x, y, rcond=None)[0]
        prediction = float(fitted[0] + fitted[1] * changes.iloc[index - 1])
        innovations.iloc[index] = float(changes.iloc[index] - prediction)
    return innovations


def beta_coefficients(y: np.ndarray, market: np.ndarray, vix: np.ndarray) -> tuple[float, float]:
    design = np.column_stack([np.ones(len(y)), market, vix])
    coefficients = np.linalg.lstsq(design, y, rcond=None)[0]
    return float(coefficients[1]), float(coefficients[2])


def zscore(series: pd.Series) -> pd.Series:
    std = float(series.std(ddof=1))
    if not math.isfinite(std) or std <= 0:
        return pd.Series(0.0, index=series.index)
    return (series - float(series.mean())) / std


CONTROL_COLUMNS = ["market_beta", "mom7", "mom28", "vol28", "max28", "log_volume30"]


def build_panel(bars: dict[str, pd.DataFrame], innovations: pd.Series, stage: str, window: int) -> pd.DataFrame:
    start, end = map(pd.Timestamp, STAGES[stage])
    decisions = pd.date_range(start, end, freq="7D", inclusive="left")
    weekly_returns = pd.DataFrame(index=innovations.index, columns=SYMBOLS, dtype=float)
    for symbol, frame in bars.items():
        opens = frame["open"].reindex(innovations.index)
        weekly_returns[symbol] = np.log(opens / opens.shift(1))
    market = weekly_returns.mean(axis=1, skipna=True)
    rows: list[dict[str, Any]] = []
    for decision in decisions:
        history_dates = innovations.loc[:decision].tail(window).index
        entry = decision + pd.Timedelta(days=int(CONFIG["action_gap_days"]))
        exit_time = entry + pd.Timedelta(days=int(CONFIG["target_days"]))
        for symbol in SYMBOLS:
            frame = bars[symbol]
            if entry not in frame.index or exit_time not in frame.index or decision not in frame.index:
                continue
            history = pd.DataFrame({
                "asset": weekly_returns.loc[history_dates, symbol],
                "market": market.loc[history_dates],
                "vix": innovations.loc[history_dates],
            }).dropna()
            if len(history) != window:
                continue
            loo_market = (market.loc[history_dates] * len(SYMBOLS) - weekly_returns.loc[history_dates, symbol]) / (len(SYMBOLS) - 1)
            history["market"] = loo_market.loc[history.index]
            market_beta, vix_beta = beta_coefficients(history["asset"].to_numpy(float), history["market"].to_numpy(float), history["vix"].to_numpy(float))
            daily = frame[(frame.index >= decision - pd.Timedelta(days=30)) & (frame.index < decision)].copy()
            if len(daily) < 30:
                continue
            daily_returns = np.log(frame["open"]).diff()
            latest28 = daily_returns[(daily_returns.index > decision - pd.Timedelta(days=28)) & (daily_returns.index <= decision)].dropna()
            if len(latest28) != 28:
                continue
            median_volume = float(daily["quote_volume"].median())
            if median_volume < float(CONFIG["minimum_median_quote_volume_30d"]):
                continue
            rows.append({
                "decision_time": decision, "entry_time": entry, "exit_time": exit_time,
                "symbol": symbol, "vix_window_weeks": window, "vix_beta": vix_beta,
                "market_beta": market_beta,
                "mom7": float(np.log(frame.at[decision, "open"] / frame.at[decision - pd.Timedelta(days=7), "open"])),
                "mom28": float(np.log(frame.at[decision, "open"] / frame.at[decision - pd.Timedelta(days=28), "open"])),
                "vol28": float(latest28.std(ddof=1)), "max28": float(latest28.max()),
                "log_volume30": float(np.log(median_volume)),
                "target_return": float(frame.at[exit_time, "open"] / frame.at[entry, "open"] - 1.0),
            })
    panel = pd.DataFrame(rows)
    if panel.empty:
        return panel
    assigned: list[pd.DataFrame] = []
    for decision, group in panel.groupby("decision_time", sort=True):
        ordered = group.sort_values(["vix_beta", "symbol"]).copy()
        n = len(ordered)
        if n < int(CONFIG["minimum_rankable"]):
            continue
        ordered["beta_percentile"] = np.arange(n, dtype=float) / max(1, n - 1)
        ordered["middle_score"] = 1.0 - 2.0 * (ordered["beta_percentile"] - 0.5).abs()
        tail = max(1, int(math.ceil(n * float(CONFIG["tail_fraction"]))))
        ordered["group"] = "other"
        ordered.iloc[:tail, ordered.columns.get_loc("group")] = "low"
        ordered.iloc[-tail:, ordered.columns.get_loc("group")] = "high"
        middle_indices = ordered.sort_values(["middle_score", "symbol"], ascending=[False, True]).head(tail).index
        ordered.loc[middle_indices, "group"] = "middle"
        assigned.append(ordered)
    return pd.concat(assigned, ignore_index=True) if assigned else pd.DataFrame()


def block_ci(values: np.ndarray) -> list[float]:
    values = np.asarray(values, dtype=float)
    rng = np.random.default_rng(int(CONFIG["bootstrap"]["seed"]))
    block = int(CONFIG["bootstrap"]["block_weeks"])
    reps = int(CONFIG["bootstrap"]["repetitions"])
    means = np.empty(reps)
    for repetition in range(reps):
        chosen: list[int] = []
        while len(chosen) < len(values):
            start = int(rng.integers(0, len(values)))
            chosen.extend(((start + np.arange(block)) % len(values)).tolist())
        means[repetition] = values[np.asarray(chosen[:len(values)])].mean()
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def hac_mean(values: np.ndarray, expected_positive: bool = True) -> dict[str, float]:
    fit = sm.OLS(np.asarray(values, dtype=float), np.ones((len(values), 1))).fit(
        cov_type="HAC", cov_kwds={"maxlags": int(CONFIG["hac_maxlags"])}
    )
    coefficient = float(fit.params[0])
    two_sided = float(fit.pvalues[0])
    favorable = coefficient >= 0 if expected_positive else coefficient <= 0
    return {
        "mean": coefficient, "hac_t": float(fit.tvalues[0]), "hac_two_sided_p": two_sided,
        "hac_one_sided_p": two_sided / 2.0 if favorable else 1.0 - two_sided / 2.0,
    }


def weekly_statistics(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    weekly_rows: list[dict[str, Any]] = []
    selected_rows: list[dict[str, Any]] = []
    for decision, group in panel.groupby("decision_time", sort=True):
        middle = group[group["group"] == "middle"]
        extremes = group[group["group"].isin(["low", "high"])]
        if middle.empty or extremes.empty:
            continue
        selected = middle.sort_values(["log_volume30", "symbol"], ascending=[False, True]).iloc[0]
        ic = spearmanr(group["middle_score"], group["target_return"]).statistic
        standardized = group.copy()
        for column in ["middle_score", *CONTROL_COLUMNS]:
            standardized[column] = zscore(standardized[column])
        design = sm.add_constant(standardized[["middle_score", *CONTROL_COLUMNS]].to_numpy(float))
        controlled = np.linalg.lstsq(design, standardized["target_return"].to_numpy(float), rcond=None)[0]
        standardized["beta_center"] = standardized["beta_percentile"] - 0.5
        standardized["beta_center_sq"] = standardized["beta_center"] ** 2
        for column in ["beta_center", "beta_center_sq"]:
            standardized[column] = zscore(standardized[column])
        quadratic_design = sm.add_constant(standardized[["beta_center", "beta_center_sq", *CONTROL_COLUMNS]].to_numpy(float))
        quadratic = np.linalg.lstsq(quadratic_design, standardized["target_return"].to_numpy(float), rcond=None)[0]
        correlations = {
            column: float(spearmanr(group["middle_score"], group[column]).statistic)
            for column in CONTROL_COLUMNS
        }
        middle_return = float(middle["target_return"].mean())
        extreme_return = float(extremes["target_return"].mean())
        weekly_rows.append({
            "decision_time": decision, "rankable": int(len(group)),
            "middle_return": middle_return, "extremes_return": extreme_return,
            "middle_minus_extremes": middle_return - extreme_return,
            "middle_score_rank_ic": float(ic),
            "controlled_middle_score_slope": float(controlled[1]),
            "quadratic_beta_squared_slope": float(quadratic[2]),
            **{f"score_{key}_spearman": value for key, value in correlations.items()},
            "selected_symbol": str(selected["symbol"]),
            "selected_gross_return": float(selected["target_return"]),
        })
        weekly_hurdle = (1.0 + float(CONFIG["annual_full_plan_hurdle"])) ** (7.0 / 365.0) - 1.0
        full_plan = float(CONFIG["economic_notional_fraction"]) * (
            float(selected["target_return"]) - float(CONFIG["stress_round_trip_underlying"])
        ) - weekly_hurdle
        selected_rows.append({
            "decision_time": decision, "entry_time": selected["entry_time"], "exit_time": selected["exit_time"],
            "symbol": str(selected["symbol"]), "gross_return": float(selected["target_return"]),
            "full_plan_after_cost_and_hurdle": full_plan,
        })
    return pd.DataFrame(weekly_rows), pd.DataFrame(selected_rows)


def summarize(panel: pd.DataFrame) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    weekly, selected = weekly_statistics(panel)
    spread = weekly["middle_minus_extremes"].to_numpy(float)
    proxy = selected["full_plan_after_cost_and_hurdle"].to_numpy(float)
    midpoint = len(weekly) // 2
    ic = hac_mean(weekly["middle_score_rank_ic"].to_numpy(float), expected_positive=True)
    controlled = hac_mean(weekly["controlled_middle_score_slope"].to_numpy(float), expected_positive=True)
    quadratic = hac_mean(weekly["quadratic_beta_squared_slope"].to_numpy(float), expected_positive=False)
    symbol_summary = selected.groupby("symbol")["full_plan_after_cost_and_hurdle"].agg(["count", "mean", "sum"])
    positive = symbol_summary[symbol_summary["sum"] > 0]
    total_positive = float(positive["sum"].sum())
    maximum_share = float(positive["sum"].max() / total_positive) if total_positive > 0 else 1.0
    correlation_columns = [f"score_{column}_spearman" for column in CONTROL_COLUMNS]
    summary = {
        "weeks": int(len(weekly)),
        "panel_rows": int(len(panel)),
        "rankable": {"minimum": int(weekly["rankable"].min()), "median": float(weekly["rankable"].median()), "maximum": int(weekly["rankable"].max())},
        "spread": {
            "mean": float(spread.mean()), "block_bootstrap_95pct": block_ci(spread),
            "positive_fraction": float((spread > 0).mean()),
            "first_half_mean": float(spread[:midpoint].mean()), "second_half_mean": float(spread[midpoint:].mean()),
        },
        "rank_ic": ic,
        "controlled_middle_score_slope": controlled,
        "quadratic_beta_squared_slope": quadratic,
        "single_leg_proxy": {
            "mean_after_cost_and_hurdle": float(proxy.mean()), "block_bootstrap_95pct": block_ci(proxy),
            "positive_fraction": float((proxy > 0).mean()),
            "first_half_mean": float(proxy[:midpoint].mean()), "second_half_mean": float(proxy[midpoint:].mean()),
            "selected_symbols": int(len(symbol_summary)),
            "positive_symbol_fraction": float((symbol_summary["mean"] > 0).mean()),
            "maximum_positive_contribution_share": maximum_share,
        },
        "score_control_correlation": {
            "median_absolute_by_control": {
                column.replace("score_", "").replace("_spearman", ""): float(weekly[column].abs().median())
                for column in correlation_columns
            },
            "maximum_median_absolute": float(max(weekly[column].abs().median() for column in correlation_columns)),
        },
    }
    return summary, weekly, selected


def stage_authorized(stage: str) -> None:
    if stage == "evaluation" and read_json(HERE / "development_gate.json")["status"] != "PASS":
        raise RuntimeError("evaluation remains sealed")
    if stage == "confirmation" and read_json(HERE / "evaluation_gate.json")["status"] != "PASS":
        raise RuntimeError("confirmation remains sealed")


def analysis_core(stage: str) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    bars, vix, _exchange = load_data()
    innovations = weekly_vix_innovations(vix)
    summaries: dict[str, Any] = {}
    outputs: dict[str, pd.DataFrame] = {}
    hashes: dict[str, str] = {}
    for name, window in WINDOWS.items():
        panel = build_panel(bars, innovations, stage, window)
        summary, weekly, selected = summarize(panel)
        summaries[name] = summary
        for kind, frame in [(f"{name}_panel", panel), (f"{name}_weekly", weekly), (f"{name}_selected", selected)]:
            outputs[kind] = frame
            raw = frame.to_csv(index=False, date_format="%Y-%m-%dT%H:%M:%SZ").encode("utf-8")
            hashes[f"{stage}_{kind}.csv"] = digest_bytes(raw)
    core = {
        "stage": stage,
        "period": {"start": STAGES[stage][0], "end_exclusive": STAGES[stage][1]},
        "data_quality_digest": read_json(HERE / "data_quality.json")["content_digest"],
        "summaries": summaries,
        "csv_sha256": hashes,
        "search_disclosure": {
            "selectable_primary_configurations": 1,
            "main": "36-week market-controlled VIX innovation beta; middle 20%",
            "diagnostics_only": ["26-week beta", "52-week beta"],
            "all_periods_post_publication": True,
            "prior_broad_market_path_exposure": True,
        },
    }
    return core, outputs


def command_analyze(args: argparse.Namespace) -> None:
    assert_checkpoint()
    stage_authorized(args.stage)
    if read_json(HERE / "data_quality.json")["status"] != "PASS":
        raise RuntimeError("data quality is not PASS")
    core, outputs = analysis_core(args.stage)
    for name, frame in outputs.items():
        (HERE / f"{args.stage}_{name}.csv").write_bytes(
            frame.to_csv(index=False, date_format="%Y-%m-%dT%H:%M:%SZ").encode("utf-8")
        )
    write_json(HERE / f"{args.stage}.json", {"generated_at_utc": now_utc(), **core})
    main = core["summaries"]["primary_36w"]
    print(json.dumps({"stage": args.stage, "spread": main["spread"]["mean"], "proxy": main["single_leg_proxy"]["mean_after_cost_and_hurdle"]}))


def gate_checks(stage: str, result: dict[str, Any]) -> dict[str, bool]:
    main = result["summaries"]["primary_36w"]
    spread = main["spread"]
    proxy = main["single_leg_proxy"]
    return {
        "data_quality_pass": read_json(HERE / "data_quality.json")["status"] == "PASS",
        "all_action_weeks_present": main["weeks"] == EXPECTED_WEEKS[stage],
        "median_rankable_at_least_20": main["rankable"]["median"] >= int(CONFIG["minimum_rankable"]),
        "spread_mean_positive": spread["mean"] > 0,
        "spread_bootstrap_lower_positive": spread["block_bootstrap_95pct"][0] > 0,
        "spread_positive_fraction_at_least_55pct": spread["positive_fraction"] >= float(CONFIG["minimum_positive_spread_fraction"]),
        "rank_ic_positive": main["rank_ic"]["mean"] > 0,
        "rank_ic_one_sided_hac_p_lt_10pct": main["rank_ic"]["hac_one_sided_p"] < 0.10,
        "controlled_slope_positive": main["controlled_middle_score_slope"]["mean"] > 0,
        "controlled_slope_one_sided_hac_p_lt_10pct": main["controlled_middle_score_slope"]["hac_one_sided_p"] < 0.10,
        "quadratic_concave": main["quadratic_beta_squared_slope"]["mean"] < 0,
        "quadratic_concavity_one_sided_hac_p_lt_10pct": main["quadratic_beta_squared_slope"]["hac_one_sided_p"] < 0.10,
        "proxy_mean_after_cost_hurdle_positive": proxy["mean_after_cost_and_hurdle"] > 0,
        "proxy_bootstrap_lower_positive": proxy["block_bootstrap_95pct"][0] > 0,
        "spread_both_halves_positive": spread["first_half_mean"] > 0 and spread["second_half_mean"] > 0,
        "proxy_both_halves_positive": proxy["first_half_mean"] > 0 and proxy["second_half_mean"] > 0,
        "diagnostic_26w_spread_nonnegative": result["summaries"]["diagnostic_26w"]["spread"]["mean"] >= 0,
        "diagnostic_52w_spread_nonnegative": result["summaries"]["diagnostic_52w"]["spread"]["mean"] >= 0,
        "proxy_selected_symbol_breadth": proxy["selected_symbols"] >= int(CONFIG["minimum_selected_symbols"]),
        "proxy_positive_symbol_fraction": proxy["positive_symbol_fraction"] >= float(CONFIG["minimum_positive_symbol_fraction"]),
        "proxy_contribution_not_concentrated": proxy["maximum_positive_contribution_share"] <= float(CONFIG["maximum_positive_contribution_share"]),
        "score_not_control_duplicate": main["score_control_correlation"]["maximum_median_absolute"] < float(CONFIG["maximum_abs_score_control_correlation"]),
    }


ECONOMIC_CHECKS = {"spread_mean_positive", "proxy_mean_after_cost_hurdle_positive"}


def command_gate(args: argparse.Namespace) -> None:
    result = read_json(HERE / f"{args.stage}.json")
    checks = gate_checks(args.stage, result)
    payload = {
        "generated_at_utc": now_utc(), "stage": args.stage,
        "status": "PASS" if all(checks.values()) else "FAIL", "checks": checks,
        "failed_checks": [key for key, value in checks.items() if not value],
        "economic_failed_checks": [key for key in ECONOMIC_CHECKS if not checks.get(key, True)],
        "result_digest": result["content_digest"],
    }
    write_json(HERE / f"{args.stage}_gate.json", payload)
    print(json.dumps({"stage": args.stage, "status": payload["status"], "failed": payload["failed_checks"]}))


def command_conclude(_args: argparse.Namespace) -> None:
    assert_checkpoint()
    available = [stage for stage in STAGES if (HERE / f"{stage}.json").exists()]
    gates = {stage: read_json(HERE / f"{stage}_gate.json") for stage in available}
    all_pass = len(gates) == 3 and all(gate["status"] == "PASS" for gate in gates.values())
    any_economic_failure = any(gate["economic_failed_checks"] for gate in gates.values())
    conclusion = "SUPPORTS_WITHIN_SCOPE" if all_pass else ("DOES_NOT_SUPPORT" if any_economic_failure else "INSUFFICIENT_EVIDENCE")
    payload = {
        "generated_at_utc": now_utc(), "conclusion": conclusion,
        "claim": "Predictive relationship only; no strategy qualification or long-term profitability claim",
        "available_stages": available,
        "stage_gate_status": {stage: gate["status"] for stage, gate in gates.items()},
        "stage_failed_checks": {stage: gate["failed_checks"] for stage, gate in gates.items()},
        "next_step": (
            "Open a separate actual-funding strategy-candidate question" if conclusion == "SUPPORTS_WITHIN_SCOPE" else
            "No strategy conversion; family stop remains binding"
        ),
        "product_effects": "NONE",
    }
    write_json(HERE / "results.json", payload)
    print(json.dumps({"conclusion": conclusion, "available_stages": available}))


def command_validate(_args: argparse.Namespace) -> None:
    assert_checkpoint()
    checks: dict[str, bool] = {
        "data_quality_pass": read_json(HERE / "data_quality.json")["status"] == "PASS",
        "source_manifest_present": (HERE / "source_manifest.json").exists(),
    }
    for stage in STAGES:
        path = HERE / f"{stage}.json"
        if not path.exists():
            continue
        stored = read_json(path)
        recomputed, _ = analysis_core(stage)
        stored_core = {key: value for key, value in stored.items() if key not in {"generated_at_utc", "content_digest"}}
        checks[f"{stage}_economics_recomputed"] = digest_value(stored_core) == digest_value(recomputed)
        checks[f"{stage}_gate_bound"] = read_json(HERE / f"{stage}_gate.json")["result_digest"] == stored["content_digest"]
        for name, expected in stored["csv_sha256"].items():
            checks[f"{name}_identity"] = digest_file(HERE / name) == expected
    if (HERE / "results.json").exists():
        result = read_json(HERE / "results.json")
        checks["valid_conclusion"] = result["conclusion"] in {
            "SUPPORTS_WITHIN_SCOPE", "DOES_NOT_SUPPORT", "INSUFFICIENT_EVIDENCE", "CANNOT_DETERMINE"
        }
        checks["no_strategy_handoff_claim"] = "strategy qualification" in result["claim"]
    payload = {
        "validated_at_utc": now_utc(), "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks, "json_files_checked": len(list(HERE.glob("*.json"))),
        "csv_files_checked": len(list(HERE.glob("*.csv"))),
    }
    write_json(HERE / "validation.json", payload)
    print(json.dumps({"status": payload["status"], "checks": checks}))
    if payload["status"] != "PASS":
        raise RuntimeError("validation failed")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Intermediate VIX-beta next-week predictability")
    sub = root.add_subparsers(dest="command", required=True)
    sub.add_parser("checkpoint").set_defaults(func=command_checkpoint)
    sub.add_parser("fetch").set_defaults(func=command_fetch)
    sub.add_parser("inspect").set_defaults(func=command_inspect)
    for name, function in (("analyze", command_analyze), ("gate", command_gate)):
        item = sub.add_parser(name)
        item.add_argument("--stage", choices=tuple(STAGES), required=True)
        item.set_defaults(func=function)
    sub.add_parser("conclude").set_defaults(func=command_conclude)
    sub.add_parser("validate").set_defaults(func=command_validate)
    return root


if __name__ == "__main__":
    arguments = parser().parse_args()
    arguments.func(arguments)
