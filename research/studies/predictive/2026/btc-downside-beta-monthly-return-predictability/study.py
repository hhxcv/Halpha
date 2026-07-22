from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import platform
import sys
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
IVOL_DIR = HERE.parent / "idiosyncratic-volatility-monthly-return-predictability"
IVOL_STUDY = IVOL_DIR / "study.py"
Q18_STUDY = HERE.parents[2] / "strategy-candidate/2026/high-volatility-ten-week-loser-weekly-one-shot-long/study.py"
UNIVERSE_PATH = HERE.parents[3] / "market-universe/universe.csv"
CACHE_ROOT = Path(
    "D:/projects/Codex/CodexHome/research-data/halpha/"
    "btc-downside-beta-monthly-return-predictability/2026-07-22-v1"
)


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load source adapter: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ivol = load_module(IVOL_STUDY, "halpha_downbeta_ivol_adapter")
q18 = load_module(Q18_STUDY, "halpha_downbeta_2025_adapter")
SYMBOLS = list(ivol.SYMBOLS)
CATEGORY_MEMBERS = dict(ivol.CATEGORY_MEMBERS)
SYMBOL_TO_CATEGORY = dict(ivol.SYMBOL_TO_CATEGORY)
STAGES = {
    "development": ("2022-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
    "evaluation": ("2024-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
    "confirmation": ("2025-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
}
VARIANTS = {"down_beta45": 45, "down_beta60": 60, "down_beta90": 90}
CONTROL_COLUMNS = ["beta60", "tvol60", "mom60", "max28", "log_volume30"]
CONFIG = {
    "predictor_id": "RESEARCH_BTC_DOWN_BETA60_MONTHLY_RETURN_V1",
    "main_variant": "down_beta60",
    "minimum_negative_btc_days": 15,
    "minimum_rankable_symbols": 20,
    "minimum_median_quote_volume_30d": 10_000_000.0,
    "history_returns": 120,
    "tail_fraction": 0.20,
    "gap_full_days": 1,
    "notional_fraction": 0.25,
    "stress_round_trip_underlying": 0.0052,
    "annual_full_plan_hurdle": 0.04,
    "bootstrap": {"block_months": 3, "repetitions": 5000, "seed": 20260722},
    "hac_maxlags": 3,
}
FROZEN_FILES = ["README.md", "sources.md", "preregistration.md", "study.py"]


def iso_now() -> str:
    return pd.Timestamp.now(tz="UTC").isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(value).isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, float):
        return None if not math.isfinite(value) else value
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def canonical_digest(value: Any) -> str:
    payload = dict(value)
    payload.pop("content_digest", None)
    raw = json.dumps(jsonable(payload), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    payload = jsonable(value)
    payload["content_digest"] = canonical_digest(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def source_entries() -> list[dict[str, Any]]:
    paths = [
        (IVOL_STUDY, "reused 2022-2024 public daily-data adapter"),
        (IVOL_DIR / "checkpoint.json", "frozen prior adapter identity"),
        (IVOL_DIR / "source_reuse_manifest.json", "public source identity chain"),
        (Q18_STUDY, "reused 2025 public daily-data stitching adapter"),
        (q18.EVAL_SOURCE / "source_manifest_evaluation.json", "2025 public input manifest"),
        (q18.EVAL_SOURCE / "data_quality_evaluation.json", "2025 public input quality"),
        (UNIVERSE_PATH, "frozen mature target universe and categories"),
    ]
    output: list[dict[str, Any]] = []
    for path, role in paths:
        if not path.exists():
            raise RuntimeError(f"missing source identity: {path}")
        output.append({"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": sha256_file(path), "role": role})
    return output


def command_checkpoint(_args: argparse.Namespace) -> None:
    if (HERE / "checkpoint.json").exists():
        checkpoint = ensure_checkpoint()
        print(json.dumps({"reused": True, "digest": checkpoint["content_digest"]}))
        return
    reuse = {"created_at_utc": iso_now(), "entries": source_entries()}
    write_json(HERE / "source_reuse_manifest.json", reuse)
    payload = {
        "created_at_utc": iso_now(),
        "baseline_commit": "0bdfeffa616260cebd2d2188ddc8deb9e85c77f4",
        "formal_strategy_background": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP",
        "research_kind": "PREDICTIVE",
        "question": "Does trailing BTC downside beta positively predict next-month mature-perpetual returns incrementally?",
        "hypothesis_direction": "positive downside-beta slope, high-minus-low spread and rank IC",
        "stages": {key: list(value) for key, value in STAGES.items()},
        "config": CONFIG,
        "universe": {"symbols": SYMBOLS, "categories": CATEGORY_MEMBERS, "market_proxy": "BTCUSDT"},
        "family_stop_rule": "Any stage failure seals later stages and forbids adjacent beta/window/tail searches.",
        "frozen_file_sha256": {name: sha256_file(HERE / name) for name in FROZEN_FILES},
        "source_reuse_digest": read_json(HERE / "source_reuse_manifest.json")["content_digest"],
        "cache_root": str(CACHE_ROOT),
        "environment": {
            "python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
            "scipy": scipy.__version__, "statsmodels": statsmodels.__version__,
        },
    }
    write_json(HERE / "checkpoint.json", payload)
    print(json.dumps({"reused": False, "digest": read_json(HERE / "checkpoint.json")["content_digest"]}))


def ensure_checkpoint() -> dict[str, Any]:
    checkpoint = read_json(HERE / "checkpoint.json")
    if checkpoint.get("content_digest") != canonical_digest(checkpoint):
        raise RuntimeError("checkpoint digest mismatch")
    if checkpoint.get("config") != CONFIG or checkpoint.get("stages") != {key: list(value) for key, value in STAGES.items()}:
        raise RuntimeError("checkpoint differs from fixed configuration")
    for name, expected in checkpoint["frozen_file_sha256"].items():
        if sha256_file(HERE / name) != expected:
            raise RuntimeError(f"frozen file changed: {name}")
    reuse = read_json(HERE / "source_reuse_manifest.json")
    if reuse.get("content_digest") != canonical_digest(reuse) or reuse["content_digest"] != checkpoint["source_reuse_digest"]:
        raise RuntimeError("source reuse identity mismatch")
    for item in reuse["entries"]:
        path = Path(item["path"])
        if not path.exists() or path.stat().st_size != item["bytes"] or sha256_file(path) != item["sha256"]:
            raise RuntimeError(f"reused source changed: {path}")
    return checkpoint


def stage_authorized(stage: str) -> None:
    prior = {"evaluation": "development", "confirmation": "evaluation"}.get(stage)
    if prior and (not (HERE / f"{prior}_gate.json").exists() or read_json(HERE / f"{prior}_gate.json")["status"] != "PASS"):
        raise RuntimeError(f"{stage} remains sealed until {prior} PASS")


def request_json(url: str) -> bytes:
    error: Exception | None = None
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Halpha-Research/1.0"})
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
            json.loads(raw)
            return raw
        except Exception as exc:
            error = exc
            if attempt < 3:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"request failed: {url}") from error


def command_fetch(args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    stage_authorized(args.stage)
    start, end = map(pd.Timestamp, STAGES[args.stage])
    cursor = int((start - pd.Timedelta(days=130)).timestamp() * 1000)
    end_ms = int((end + pd.Timedelta(days=2)).timestamp() * 1000)
    pages: list[dict[str, Any]] = []
    raw_root = CACHE_ROOT / args.stage / "BTCUSDT" / "raw"
    page = 0
    while cursor < end_ms:
        query = urllib.parse.urlencode({"symbol": "BTCUSDT", "interval": "1d", "startTime": cursor, "endTime": end_ms - 1, "limit": 1500})
        url = f"https://fapi.binance.com/fapi/v1/klines?{query}"
        raw = request_json(url)
        rows = json.loads(raw)
        if not rows:
            break
        path = raw_root / f"openTime-{page:03d}.json"
        if path.exists() and path.read_bytes() != raw:
            raise RuntimeError(f"refusing to overwrite different raw page: {path}")
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        pages.append({
            "url": url, "path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "rows": len(rows), "first_time_ms": int(rows[0][0]), "last_time_ms": int(rows[-1][0]),
        })
        next_cursor = int(rows[-1][0]) + 1
        if next_cursor <= cursor:
            raise RuntimeError("non-advancing BTC pagination")
        cursor = next_cursor
        page += 1
    manifest = {
        "accessed_at_utc": iso_now(), "stage": args.stage, "checkpoint_digest": checkpoint["content_digest"],
        "source": "Binance public USD-M REST klines; no credentials", "symbol": "BTCUSDT", "interval": "1d",
        "requested_start": (start - pd.Timedelta(days=130)).isoformat(), "requested_end_exclusive": (end + pd.Timedelta(days=2)).isoformat(),
        "pages": pages,
    }
    write_json(HERE / f"source_manifest_{args.stage}.json", manifest)
    print(json.dumps({"stage": args.stage, "pages": len(pages), "rows": sum(item["rows"] for item in pages), "digest": read_json(HERE / f"source_manifest_{args.stage}.json")["content_digest"]}))


def load_btc(stage: str) -> pd.DataFrame:
    manifest = read_json(HERE / f"source_manifest_{stage}.json")
    rows: list[Any] = []
    for item in manifest["pages"]:
        path = Path(item["path"])
        raw = path.read_bytes()
        if len(raw) != item["bytes"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise RuntimeError(f"BTC source identity mismatch: {path}")
        rows.extend(json.loads(raw))
    frame = pd.DataFrame(rows, columns=[
        "open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume",
        "trade_count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
    ])
    frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    for column in ["open", "high", "low", "close", "quote_volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    return frame.drop_duplicates("open_time").sort_values("open_time").set_index("open_time")


def load_alt_bars(stage: str) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    if stage in {"development", "evaluation"}:
        bars, _funding, metadata = ivol.ptv.load_stage(stage)
        return bars, metadata
    bars, _funding, metadata = q18.load_stage("evaluation")
    return bars, metadata


def month_entries(stage: str) -> pd.DatetimeIndex:
    start, end = map(pd.Timestamp, STAGES[stage])
    return pd.date_range(start, end, freq="MS", inclusive="left")


def daily_frame(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.sort_index().copy().reindex(pd.date_range(raw.index.min(), raw.index.max(), freq="1D"))
    frame["log_return"] = np.log(frame["close"]).diff()
    frame["median_quote_volume_30d"] = frame["quote_volume"].rolling(30, min_periods=30).median()
    return frame


def beta(y: np.ndarray, x: np.ndarray) -> float:
    variance = float(np.var(x, ddof=1))
    return float(np.cov(y, x, ddof=1)[0, 1] / variance) if variance > 0.0 else math.nan


def build_panel(bars: dict[str, pd.DataFrame], btc_raw: pd.DataFrame, stage: str) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    daily = {symbol: daily_frame(frame) for symbol, frame in bars.items()}
    btc = daily_frame(btc_raw)
    rows: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    history = int(CONFIG["history_returns"])
    for entry in month_entries(stage):
        cutoff = entry - pd.Timedelta(days=2)
        exit_time = entry + pd.offsets.MonthBegin(1)
        dates = pd.date_range(cutoff - pd.Timedelta(days=history), cutoff, freq="1D")
        if not dates.isin(btc.index).all() or btc.loc[dates, ["close"]].isna().any().any():
            audit.append({"entry_time": entry, "status": "BTC_HISTORY_INCOMPLETE"})
            continue
        btc_returns = np.diff(np.log(btc.loc[dates, "close"].to_numpy(float)))
        month_rows: list[dict[str, Any]] = []
        future_missing: list[str] = []
        for symbol in SYMBOLS:
            frame = daily[symbol]
            if not dates.isin(frame.index).all():
                continue
            history_frame = frame.loc[dates]
            if history_frame[["open", "high", "low", "close", "quote_volume"]].isna().any().any():
                continue
            volume = float(frame.at[cutoff, "median_quote_volume_30d"])
            if not math.isfinite(volume) or volume < CONFIG["minimum_median_quote_volume_30d"]:
                continue
            if entry not in frame.index or exit_time not in frame.index or pd.isna(frame.at[entry, "open"]) or pd.isna(frame.at[exit_time, "open"]):
                future_missing.append(symbol)
                continue
            y = np.diff(np.log(history_frame["close"].to_numpy(float)))
            features: dict[str, float] = {}
            valid = True
            for name, lookback in VARIANTS.items():
                mask = btc_returns[-lookback:] < 0.0
                if int(mask.sum()) < CONFIG["minimum_negative_btc_days"]:
                    valid = False
                    break
                features[name] = beta(y[-lookback:][mask], btc_returns[-lookback:][mask])
            if not valid or not all(math.isfinite(value) for value in features.values()):
                continue
            month_rows.append({
                "entry_time": entry, "signal_cutoff": cutoff, "exit_time": exit_time, "holding_days": int((exit_time-entry).days),
                "symbol": symbol, "category": SYMBOL_TO_CATEGORY[symbol], **features,
                "beta60": beta(y[-60:], btc_returns[-60:]), "tvol60": float(np.std(y[-60:], ddof=1)),
                "mom60": float(np.sum(y[-60:])), "max28": float(np.max(y[-28:])), "log_volume30": float(np.log(volume)),
                "target_asset_return": float(frame.at[exit_time, "open"] / frame.at[entry, "open"] - 1.0),
            })
        if len(month_rows) < CONFIG["minimum_rankable_symbols"]:
            audit.append({"entry_time": entry, "status": "TOO_FEW_RANKABLE", "rankable": len(month_rows)})
            continue
        if future_missing:
            audit.append({"entry_time": entry, "status": "FUTURE_TARGET_MISSING", "symbols": sorted(future_missing)})
            continue
        market_return = float(np.mean([item["target_asset_return"] for item in month_rows]))
        for item in month_rows:
            item["target_market_return"] = market_return
            item["target_excess_return"] = item["target_asset_return"] - market_return
            rows.append(item)
        audit.append({"entry_time": entry, "status": "ACTION", "rankable": len(month_rows)})
    if not rows:
        raise RuntimeError(f"empty panel: {stage}")
    panel = pd.DataFrame(rows).replace([np.inf, -np.inf], np.nan)
    required = list(VARIANTS) + CONTROL_COLUMNS + ["target_asset_return", "target_excess_return"]
    if panel[required].isna().any().any():
        raise RuntimeError("non-finite panel")
    return panel.sort_values(["entry_time", "symbol"]).reset_index(drop=True), audit


def block_ci(values: np.ndarray) -> list[float]:
    values = np.asarray(values, float)
    rng = np.random.default_rng(CONFIG["bootstrap"]["seed"] + len(values))
    means = np.empty(CONFIG["bootstrap"]["repetitions"])
    block = CONFIG["bootstrap"]["block_months"]
    for index in range(len(means)):
        chosen: list[int] = []
        while len(chosen) < len(values):
            start = int(rng.integers(0, len(values)))
            chosen.extend(((start + np.arange(block)) % len(values)).tolist())
        means[index] = float(values[np.asarray(chosen[:len(values)])].mean())
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def summary(series: pd.Series) -> dict[str, Any]:
    values = series.to_numpy(float)
    return {"observations": len(values), "mean": float(values.mean()), "median": float(np.median(values)), "bootstrap_95pct": block_ci(values), "positive_fraction": float(np.mean(values > 0.0))}


def monthly_variant(panel: pd.DataFrame, score: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for entry, frame in panel.groupby("entry_time", sort=True):
        ordered = frame.sort_values([score, "symbol"])
        tail = max(1, int(math.ceil(len(frame) * CONFIG["tail_fraction"])))
        low, high = ordered.head(tail), ordered.tail(tail)
        high_beta = frame.sort_values(["beta60", "symbol"], ascending=[False, True]).head(tail)
        high_vol = frame.sort_values(["tvol60", "symbol"], ascending=[False, True]).head(tail)
        high_return = float(high["target_asset_return"].mean())
        days = int(frame["holding_days"].iloc[0])
        proxy = CONFIG["notional_fraction"] * (high_return - CONFIG["stress_round_trip_underlying"]) - CONFIG["annual_full_plan_hurdle"] * days / 365.0
        rows.append({
            "entry_time": entry, "variant": score, "eligible_count": len(frame), "tail_count": tail,
            "low_symbols": "|".join(low["symbol"]), "high_symbols": "|".join(high["symbol"]),
            "low_return": float(low["target_asset_return"].mean()), "high_return": high_return,
            "high_minus_low_return": high_return - float(low["target_asset_return"].mean()),
            "rank_ic": float(spearmanr(frame[score], frame["target_excess_return"]).statistic),
            "high_long_proxy": proxy,
            "high_down_minus_high_total_beta": high_return - float(high_beta["target_asset_return"].mean()),
            "high_down_minus_high_total_vol": high_return - float(high_vol["target_asset_return"].mean()),
        })
    return pd.DataFrame(rows)


def summarize_monthly(frame: pd.DataFrame) -> dict[str, Any]:
    return {key: summary(frame[key]) for key in ["high_minus_low_return", "rank_ic", "high_long_proxy", "high_down_minus_high_total_beta", "high_down_minus_high_total_vol"]} | {"action_months": len(frame)}


def fama_macbeth(panel: pd.DataFrame, controlled: bool) -> tuple[dict[str, Any], pd.DataFrame]:
    predictors = [CONFIG["main_variant"]] + (CONTROL_COLUMNS if controlled else [])
    rows: list[dict[str, Any]] = []
    for entry, frame in panel.groupby("entry_time", sort=True):
        design = pd.DataFrame(index=frame.index)
        for column in predictors:
            scale = float(frame[column].std(ddof=1))
            if scale <= 0.0 or not math.isfinite(scale):
                raise RuntimeError(f"invalid cross-sectional scale: {entry} {column}")
            design[column] = (frame[column] - frame[column].mean()) / scale
        model = sm.OLS(frame["target_excess_return"], sm.add_constant(design, has_constant="add")).fit()
        rows.append({"entry_time": entry, **{name: float(model.params[name]) for name in predictors}})
    coefficients = pd.DataFrame(rows)
    values = coefficients[CONFIG["main_variant"]].to_numpy(float)
    hac = sm.OLS(values, np.ones((len(values), 1))).fit(cov_type="HAC", cov_kwds={"maxlags": CONFIG["hac_maxlags"]})
    mean = float(hac.params[0]); two = float(hac.pvalues[0])
    one_positive = two / 2.0 if mean > 0.0 else 1.0 - two / 2.0
    return {"controlled": controlled, "months": len(values), "predictors": predictors, "coefficient_mean": mean, "hac_standard_error": float(hac.bse[0]), "hac_t": float(hac.tvalues[0]), "hac_two_sided_p": two, "hac_one_sided_positive_p": one_positive, "bootstrap_95pct": block_ci(values)}, coefficients


def selected_high(panel: pd.DataFrame) -> pd.DataFrame:
    output: list[pd.DataFrame] = []
    for _entry, frame in panel.groupby("entry_time", sort=True):
        tail = max(1, int(math.ceil(len(frame) * CONFIG["tail_fraction"])))
        chosen = frame.sort_values([CONFIG["main_variant"], "symbol"], ascending=[False, True]).head(tail).copy()
        output.append(chosen)
    return pd.concat(output, ignore_index=True)


def breadth(selected: pd.DataFrame) -> dict[str, Any]:
    by = selected.groupby(["symbol", "category"])["target_asset_return"].agg(["size", "mean", "sum"]).reset_index()
    positive = by[by["sum"] > 0.0]
    total = float(positive["sum"].sum())
    return {"selected_symbols": int(by["symbol"].nunique()), "selected_categories": int(by["category"].nunique()), "maximum_positive_contribution_share": float(positive["sum"].max()/total) if total > 0 else 1.0, "by_symbol": by.to_dict(orient="records")}


def command_self_test(_args: argparse.Namespace) -> None:
    btc = np.linspace(-0.03, 0.03, 60)
    y = 1.5 * btc
    mask = btc < 0.0
    estimate = beta(y[mask], btc[mask])
    if abs(estimate - 1.5) > 1e-10:
        raise RuntimeError("downside beta orientation failed")
    values = np.arange(24.0)
    if block_ci(values) != block_ci(values):
        raise RuntimeError("bootstrap not deterministic")
    print(json.dumps({"status": "PASS", "synthetic_down_beta": estimate, "bootstrap_deterministic": True}))


def command_prepare(args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint(); stage_authorized(args.stage)
    bars, metadata = load_alt_bars(args.stage)
    panel, audit = build_panel(bars, load_btc(args.stage), args.stage)
    counts = panel.groupby("entry_time")["symbol"].nunique()
    failures = [item for item in audit if item["status"] not in {"ACTION", "TOO_FEW_RANKABLE"}]
    payload = {
        "checked_at_utc": iso_now(), "stage": args.stage,
        "status": "PASS" if not failures and metadata.get("overlap_mismatch_rows", 0) == 0 else "FAIL",
        "checkpoint_digest": checkpoint["content_digest"], "source_overlap": metadata,
        "scheduled_months": len(month_entries(args.stage)), "action_months": int(panel["entry_time"].nunique()),
        "minimum_rankable": int(counts.min()), "maximum_rankable": int(counts.max()), "failures": failures, "month_audit": audit,
    }
    panel.to_csv(HERE / f"{args.stage}_panel.csv", index=False)
    write_json(HERE / f"data_quality_{args.stage}.json", payload)
    print(json.dumps({"stage": args.stage, "status": payload["status"], "action_months": payload["action_months"], "minimum_rankable": payload["minimum_rankable"]}))


def command_analyze(args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint(); stage_authorized(args.stage)
    dq = read_json(HERE / f"data_quality_{args.stage}.json")
    if dq["status"] != "PASS":
        raise RuntimeError("data quality not PASS")
    panel = pd.read_csv(HERE / f"{args.stage}_panel.csv", parse_dates=["entry_time", "signal_cutoff", "exit_time"])
    monthly = {name: monthly_variant(panel, name) for name in VARIANTS}
    main = monthly[CONFIG["main_variant"]]
    uncontrolled, unc_rows = fama_macbeth(panel, False)
    controlled, ctl_rows = fama_macbeth(panel, True)
    selected = selected_high(panel)
    years = {str(year): {key: float(frame[key].mean()) for key in ["high_minus_low_return", "rank_ic", "high_long_proxy"]} for year, frame in main.groupby(main["entry_time"].dt.year)}
    payload = {
        "analyzed_at_utc": iso_now(), "stage": args.stage, "checkpoint_digest": checkpoint["content_digest"],
        "period": {"start": STAGES[args.stage][0], "end_exclusive": STAGES[args.stage][1]},
        "main": summarize_monthly(main),
        "neighbors": {name: summarize_monthly(frame) for name, frame in monthly.items() if name != CONFIG["main_variant"]},
        "regressions": {"uncontrolled": uncontrolled, "controlled": controlled}, "calendar_years": years,
        "breadth": breadth(selected),
        "limitations": ["fixed current-survivor universe", "no market-cap or delisted-coin data", "economic proxy excludes funding and intramonth margin path", "predictive evidence cannot authorize trading"],
    }
    for name, frame in monthly.items(): frame.to_csv(HERE / f"{args.stage}_{name}_monthly.csv", index=False)
    selected.to_csv(HERE / f"{args.stage}_high_selected.csv", index=False)
    unc_rows.to_csv(HERE / f"{args.stage}_fmb_uncontrolled.csv", index=False)
    ctl_rows.to_csv(HERE / f"{args.stage}_fmb_controlled.csv", index=False)
    write_json(HERE / f"{args.stage}.json", payload)
    write_json(HERE / "results.json", payload)
    print(json.dumps({"stage": args.stage, "months": payload["main"]["action_months"], "spread": payload["main"]["high_minus_low_return"]["mean"], "rank_ic": payload["main"]["rank_ic"]["mean"], "controlled_slope": controlled["coefficient_mean"], "p": controlled["hac_one_sided_positive_p"], "proxy": payload["main"]["high_long_proxy"]["mean"]}))


def gate_checks(stage: str, result: dict[str, Any], dq: dict[str, Any]) -> dict[str, bool]:
    main = result["main"]; regs = result["regressions"]; years = result["calendar_years"]; neighbors = result["neighbors"]; wide = result["breadth"]
    minimum_months = 21 if stage == "development" else 10
    return {
        "data_quality_pass": dq["status"] == "PASS", "minimum_action_months": main["action_months"] >= minimum_months,
        "minimum_20_rankable": dq["minimum_rankable"] >= 20,
        "spread_mean_positive": main["high_minus_low_return"]["mean"] > 0.0,
        "spread_bootstrap_lower_positive": main["high_minus_low_return"]["bootstrap_95pct"][0] > 0.0,
        "rank_ic_mean_positive": main["rank_ic"]["mean"] > 0.0,
        "rank_ic_bootstrap_lower_positive": main["rank_ic"]["bootstrap_95pct"][0] > 0.0,
        "uncontrolled_slope_positive_significant": regs["uncontrolled"]["coefficient_mean"] > 0.0 and regs["uncontrolled"]["hac_one_sided_positive_p"] < 0.05,
        "controlled_slope_positive_significant": regs["controlled"]["coefficient_mean"] > 0.0 and regs["controlled"]["hac_one_sided_positive_p"] < 0.05,
        "long_proxy_mean_positive": main["high_long_proxy"]["mean"] > 0.0,
        "long_proxy_bootstrap_lower_positive": main["high_long_proxy"]["bootstrap_95pct"][0] > 0.0,
        "increment_vs_total_beta_mean_positive": main["high_down_minus_high_total_beta"]["mean"] > 0.0,
        "increment_vs_total_beta_bootstrap_lower_positive": main["high_down_minus_high_total_beta"]["bootstrap_95pct"][0] > 0.0,
        "increment_vs_total_vol_mean_positive": main["high_down_minus_high_total_vol"]["mean"] > 0.0,
        "all_years_directional": all(item["high_minus_low_return"] > 0 and item["rank_ic"] > 0 and item["high_long_proxy"] > 0 for item in years.values()),
        "all_neighbors_directional": all(item["high_minus_low_return"]["mean"] > 0 and item["rank_ic"]["mean"] > 0 and item["high_long_proxy"]["mean"] > 0 for item in neighbors.values()),
        "minimum_8_symbols": wide["selected_symbols"] >= 8, "minimum_3_categories": wide["selected_categories"] >= 3,
        "max_positive_contribution_35pct": wide["maximum_positive_contribution_share"] <= 0.35,
    }


def command_gate(args: argparse.Namespace) -> None:
    ensure_checkpoint(); stage_authorized(args.stage)
    result = read_json(HERE / f"{args.stage}.json"); dq = read_json(HERE / f"data_quality_{args.stage}.json")
    checks = gate_checks(args.stage, result, dq); failed = [name for name, passed in checks.items() if not passed]
    status = "PASS" if not failed else "FAIL"
    conclusion = "INSUFFICIENT_EVIDENCE" if status == "PASS" and args.stage != "confirmation" else ("SUPPORTS_WITHIN_SCOPE" if status == "PASS" else "DOES_NOT_SUPPORT")
    payload = {"generated_at_utc": iso_now(), "stage": args.stage, "status": status, "conclusion": conclusion, "checks": checks, "failed_checks": failed, "result_digest": result["content_digest"]}
    write_json(HERE / f"{args.stage}_gate.json", payload)
    print(json.dumps({"stage": args.stage, "status": status, "conclusion": conclusion, "failed": failed}))


def command_validate(_args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint(); checks: dict[str, bool] = {"checkpoint_valid": bool(checkpoint)}
    for stage in STAGES:
        result_path = HERE / f"{stage}.json"
        if not result_path.exists(): continue
        result = read_json(result_path); gate = read_json(HERE / f"{stage}_gate.json")
        checks[f"{stage}_result_digest"] = result["content_digest"] == canonical_digest(result)
        checks[f"{stage}_gate_bound"] = gate["result_digest"] == result["content_digest"]
        checks[f"{stage}_panel_present"] = (HERE / f"{stage}_panel.csv").exists()
    payload = {"validated_at_utc": iso_now(), "status": "PASS" if all(checks.values()) else "FAIL", "checks": checks, "json_files_checked": len(list(HERE.glob("*.json"))), "csv_files_checked": len(list(HERE.glob("*.csv")))}
    write_json(HERE / "validation.json", payload); print(json.dumps({"status": payload["status"], "checks": checks}))
    if payload["status"] != "PASS": raise RuntimeError("validation failed")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="BTC downside beta monthly return predictability")
    sub = root.add_subparsers(dest="command", required=True)
    sub.add_parser("checkpoint").set_defaults(func=command_checkpoint)
    sub.add_parser("self-test").set_defaults(func=command_self_test)
    for name, function in (("fetch", command_fetch), ("prepare", command_prepare), ("analyze", command_analyze), ("gate", command_gate)):
        item = sub.add_parser(name); item.add_argument("--stage", choices=tuple(STAGES), required=True); item.set_defaults(func=function)
    sub.add_parser("validate").set_defaults(func=command_validate)
    return root


if __name__ == "__main__":
    args = parser().parse_args(); args.func(args)
