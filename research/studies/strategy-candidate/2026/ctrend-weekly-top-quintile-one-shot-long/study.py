from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import platform
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
import scipy
import sklearn
import vectorbt as vbt
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import ElasticNet


HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "category-momentum-gated-one-shot-long"
PARENT_STUDY = PARENT / "study.py"
PARENT_MANIFEST = PARENT / "source_manifest_development.json"
UNIVERSE = HERE.parents[3] / "market-universe" / "universe.csv"
CACHE_ROOT = Path("D:/projects/Codex/CodexHome/research-data/halpha/ctrend-weekly-top-quintile-one-shot-long/2026-07-22-v1")
SYMBOLS = [
    "1000XECUSDT", "AAVEUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "CRVUSDT",
    "DASHUSDT", "ENSUSDT", "ETCUSDT", "HBARUSDT", "KAVAUSDT", "LINKUSDT",
    "LTCUSDT", "NEARUSDT", "RUNEUSDT", "SNXUSDT", "SOLUSDT", "TRXUSDT",
    "UNIUSDT", "VETUSDT", "XLMUSDT", "XMRUSDT", "XRPUSDT", "ZECUSDT", "ZILUSDT",
]
FEATURES = [
    "rsi14", "stoch_rsi14", "stoch_k14", "stoch_d3", "cci20",
    "sma_3", "sma_5", "sma_10", "sma_20", "sma_50", "sma_100", "sma_200",
    "macd", "macd_diff",
    "volsma_3", "volsma_5", "volsma_10", "volsma_20", "volsma_50", "volsma_100", "volsma_200",
    "volmacd", "volmacd_diff", "chaikin21",
    "boll_low", "boll_mid", "boll_high", "boll_width",
]
VOLUME_FEATURES = [name for name in FEATURES if name.startswith("vol") or name == "chaikin21"]
NON_VOLUME_FEATURES = [name for name in FEATURES if name not in VOLUME_FEATURES]
STAGES = {
    "development": ("2023-01-02T00:00:00Z", "2024-01-01T00:00:00Z"),
    "evaluation": ("2024-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
    "confirmation": ("2025-01-01T00:00:00Z", "2026-07-01T00:00:00Z"),
}
CONFIG = {
    "strategy_id": "RESEARCH_CTREND_TOP_QUINTILE_WEEKLY_ONE_SHOT_LONG_0P5X_V1",
    "direction": "LONG_ONLY",
    "hold_days": 7,
    "notional_fraction": 0.5,
    "top_fraction": 0.2,
    "minimum_rankable_symbols": 20,
    "minimum_median_quote_volume_30d": 10_000_000.0,
    "main_training_weeks": 52,
    "elastic_net_l1_ratio": 0.5,
    "elastic_net_alpha_grid": [float(value) for value in np.logspace(-6, -1, 41)],
    "annual_capital_hurdle": 0.04,
    "cooldown_full_days": 1,
    "costs": {
        "favorable": {"fee_per_side": 0.0006, "slippage_per_side": 0.0, "funding_stress": False},
        "base": {"fee_per_side": 0.0006, "slippage_per_side": 0.0010, "funding_stress": False},
        "stress": {"fee_per_side": 0.0006, "slippage_per_side": 0.0020, "funding_stress": True},
    },
    "long_funding_stress": {"positive_cost_multiplier": 1.5, "negative_benefit_multiplier": 0.5},
    "bootstrap": {"block_weeks": 4, "repetitions": 5000, "seed": 20260722},
    "diagnostics": {
        "window26": {"training_weeks": 26, "features": "all", "combination": "elastic_net"},
        "window78": {"training_weeks": 78, "features": "all", "combination": "elastic_net"},
        "no_volume": {"training_weeks": 52, "features": "non_volume", "combination": "elastic_net"},
        "naive_all": {"training_weeks": 52, "features": "all", "combination": "naive_all"},
    },
}


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_digest(value: Any) -> str:
    return sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def write_json(path: Path, value: Any, *, digest: bool = False) -> None:
    payload = dict(value) if isinstance(value, dict) else value
    if digest:
        payload.pop("content_digest", None)
        payload["content_digest"] = canonical_digest(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def category_map() -> dict[str, str]:
    frame = pd.read_csv(UNIVERSE)
    frame = frame[(frame["market"] == "BINANCE_USD_M") & frame["symbol"].isin(SYMBOLS)]
    result = dict(zip(frame["symbol"], frame["classification_subtypes"], strict=False))
    missing = sorted(set(SYMBOLS) - set(result))
    if missing:
        raise RuntimeError(f"universe categories missing: {missing}")
    return {symbol: str(result[symbol]) for symbol in SYMBOLS}


def load_parent_module() -> Any:
    spec = importlib.util.spec_from_file_location("halpha_ctrend_parent", PARENT_STUDY)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load parent research module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_reuse_identity() -> dict[str, Any]:
    manifest = read_json(PARENT_MANIFEST)
    items: list[dict[str, Any]] = []
    total_bytes = 0
    families = ("kline_pages", "funding_archives", "mark_price_archives", "mark_price_gap_archives")
    for symbol in SYMBOLS:
        source = manifest["symbols"][symbol]
        for family in families:
            for item in source.get(family, []):
                record = {
                    "symbol": symbol, "family": family, "path": item["path"], "url": item["url"],
                    "bytes": int(item["bytes"]), "sha256": item["sha256"],
                }
                if "csv_sha256" in item:
                    record["csv_member"] = item["csv_member"]
                    record["csv_bytes"] = int(item["csv_bytes"])
                    record["csv_sha256"] = item["csv_sha256"]
                items.append(record)
                total_bytes += int(item["bytes"])
    return {
        "source_study": str(PARENT),
        "source_study_sha256": sha256_file(PARENT_STUDY),
        "source_manifest_path": str(PARENT_MANIFEST),
        "source_manifest_sha256": sha256_file(PARENT_MANIFEST),
        "source_manifest_content_digest": manifest["content_digest"],
        "files": len(items), "bytes": total_bytes, "items": items,
        "retrieval_rule": "Reuse only recorded Binance public files and require byte length plus SHA-256; no product data or credentials.",
    }


def supplement_plan() -> list[dict[str, Any]]:
    start_ms = int(pd.Timestamp("2020-06-01T00:00:00Z").timestamp() * 1000)
    end_ms = int(pd.Timestamp("2021-11-17T00:00:00Z").timestamp() * 1000) - 1
    return [
        {
            "symbol": symbol,
            "url": f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=1d&startTime={start_ms}&endTime={end_ms}&limit=1500",
            "path": str(CACHE_ROOT / "supplement" / symbol / "klines-2020-06-01_2021-11-17.json"),
        }
        for symbol in SYMBOLS
    ]


def command_checkpoint(_args: argparse.Namespace) -> None:
    if (HERE / "checkpoint.json").exists():
        raise RuntimeError("checkpoint already exists; refusing to overwrite time anchor")
    reuse = source_reuse_identity()
    reuse["created_at_utc"] = iso_now()
    write_json(HERE / "source_reuse_manifest.json", reuse, digest=True)
    payload = {
        "created_at_utc": iso_now(),
        "baseline_commit": "0bdfeffa616260cebd2d2188ddc8deb9e85c77f4",
        "formal_strategy": {"id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT", "version": "1.0.1", "instrument": "BTCUSDT-PERP"},
        "research_kind": "STRATEGY_CANDIDATE",
        "question": "Does a paper-guided 28-signal CTREND top-quintile filter qualify a user-fixed weekly one-shot perpetual LONG after realistic retail costs, funding, simple trend and market baselines, robustness, model stability, and staged time evidence?",
        "evidence_boundary": "The source paper ends in May 2022 and exact Halpha CTREND outputs are unviewed. Some underlying market paths were exposed by unrelated studies; the current-survivor universe is not point-in-time history.",
        "symbols": SYMBOLS, "categories": category_map(), "features": FEATURES,
        "stages": STAGES, "config": CONFIG,
        "source_supplement_plan": supplement_plan(),
        "stage_open_rule": "development -> evaluation -> confirmation; later-stage retrieval and output are forbidden until the prior exact-rule gate passes",
        "allowed_fixes": "Only retrieval, parsing, identity, deterministic-statistic, or implementation defects that preserve the frozen economic rule; append the old and new identities to attempts.md.",
        "forbidden_after_checkpoint": [
            "selecting favorable features, target, direction, rank cutoff, holding period, cost or training window",
            "promoting a diagnostic after seeing its result", "opening a later stage after a gate failure",
            "calling current survivors a historical point-in-time universe", "calling a positive backtest proof of long-term alpha",
        ],
        "files": {
            "study_py_sha256": sha256_file(Path(__file__)),
            "preregistration_sha256": sha256_file(HERE / "preregistration.md"),
            "sources_sha256": sha256_file(HERE / "sources.md"),
            "source_reuse_manifest_sha256": sha256_file(HERE / "source_reuse_manifest.json"),
            "universe_sha256": sha256_file(UNIVERSE),
        },
        "environment": {
            "python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
            "scipy": scipy.__version__, "scikit_learn": sklearn.__version__, "vectorbt": vbt.__version__,
        },
        "cache_root": str(CACHE_ROOT),
    }
    write_json(HERE / "checkpoint.json", payload, digest=True)
    checkpoint = read_json(HERE / "checkpoint.json")
    print(json.dumps({"checkpoint": str(HERE / "checkpoint.json"), "digest": checkpoint["content_digest"]}))


def ensure_checkpoint() -> dict[str, Any]:
    checkpoint = read_json(HERE / "checkpoint.json")
    if checkpoint["symbols"] != SYMBOLS or checkpoint["features"] != FEATURES or checkpoint["config"] != CONFIG:
        raise RuntimeError("checkpoint does not match fixed code configuration")
    current_study_sha = sha256_file(Path(__file__))
    if checkpoint["files"]["study_py_sha256"] != current_study_sha:
        amendment_path = HERE / "amendment-001.json"
        if not amendment_path.exists():
            raise RuntimeError("study.py changed after checkpoint without recorded amendment")
        amendment = read_json(amendment_path)
        if amendment["original_study_py_sha256"] != checkpoint["files"]["study_py_sha256"] or amendment["amended_study_py_sha256"] != current_study_sha:
            raise RuntimeError("study.py amendment identity mismatch")
    for name, path in (("preregistration_sha256", HERE / "preregistration.md"), ("sources_sha256", HERE / "sources.md"),
                       ("source_reuse_manifest_sha256", HERE / "source_reuse_manifest.json"), ("universe_sha256", UNIVERSE)):
        if checkpoint["files"][name] != sha256_file(path):
            raise RuntimeError(f"checkpoint identity mismatch: {name}")
    reuse = read_json(HERE / "source_reuse_manifest.json")
    if reuse["source_study_sha256"] != sha256_file(PARENT_STUDY) or reuse["source_manifest_sha256"] != sha256_file(PARENT_MANIFEST):
        raise RuntimeError("parent research identity changed")
    return checkpoint


def fetch_immutable(url: str, path: Path) -> tuple[bytes, bool]:
    response = requests.get(url, timeout=60, headers={"User-Agent": "Halpha-research/ctrend-public-data"})
    response.raise_for_status()
    raw = response.content
    if path.exists():
        existing = path.read_bytes()
        if existing != raw:
            raise RuntimeError(f"refusing to overwrite revised public response: {path}")
        return existing, True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw, False


def command_prepare(args: argparse.Namespace) -> None:
    ensure_checkpoint()
    if args.stage != "development":
        raise RuntimeError("later-stage fetch is intentionally unavailable until development PASS")
    records: list[dict[str, Any]] = []
    for item in supplement_plan():
        raw, reused = fetch_immutable(item["url"], Path(item["path"]))
        rows = json.loads(raw)
        if not isinstance(rows, list):
            raise RuntimeError(f"unexpected kline response: {item['symbol']}")
        records.append({**item, "bytes": len(raw), "sha256": sha256_bytes(raw), "rows": len(rows), "reused": reused})
    manifest = {
        "created_at_utc": iso_now(), "stage": "development", "checkpoint_digest": read_json(HERE / "checkpoint.json")["content_digest"],
        "source": "Binance public USD-M REST; no credentials", "items": records,
        "files": len(records), "bytes": sum(item["bytes"] for item in records),
    }
    write_json(HERE / "source_supplement_manifest.json", manifest, digest=True)
    bars, funding = load_all()
    dq: dict[str, Any] = {
        "checked_at_utc": iso_now(), "stage": "development", "status": "PASS", "symbols": {},
        "source_reuse_manifest_sha256": sha256_file(HERE / "source_reuse_manifest.json"),
        "source_supplement_manifest_sha256": sha256_file(HERE / "source_supplement_manifest.json"),
    }
    for symbol in SYMBOLS:
        frame = bars[symbol]
        first, last = frame.index.min(), frame.index.max()
        expected = pd.date_range(first, pd.Timestamp("2024-01-02T00:00:00Z"), freq="1D", inclusive="left")
        missing = expected.difference(frame.index)
        invalid_ohlc = int(((frame[["open", "high", "low", "close"]] <= 0).any(axis=1)).sum())
        invalid_range = int(((frame["high"] < frame[["open", "close"]].max(axis=1)) | (frame["low"] > frame[["open", "close"]].min(axis=1))).sum())
        relevant_funding = funding[symbol][(funding[symbol].index >= pd.Timestamp("2023-01-02T00:00:00Z")) &
                                            (funding[symbol].index <= pd.Timestamp("2024-01-01T00:00:00Z"))]
        missing_marks = int(relevant_funding["markPrice"].isna().sum())
        # Missing official marks are retained as explicit gaps. The frozen economic rule excludes
        # any trade spanning one and applies the preregistered 2% opportunity-level gate; it does
        # not impute a mark or invalidate otherwise complete OHLCV input.
        status = "PASS" if len(missing) == 0 and invalid_ohlc == 0 and invalid_range == 0 else "FAIL"
        if status != "PASS":
            dq["status"] = "FAIL"
        dq["symbols"][symbol] = {
            "status": status, "first_bar": first.isoformat(), "last_bar": last.isoformat(), "bars": int(len(frame)),
            "internal_missing_days": int(len(missing)), "invalid_ohlc": invalid_ohlc, "invalid_range": invalid_range,
            "development_funding_events": int(len(relevant_funding)), "missing_funding_marks": missing_marks,
        }
    write_json(HERE / "data_quality_development.json", dq, digest=True)
    print(json.dumps({"status": dq["status"], "supplement_files": len(records), "symbols": len(SYMBOLS)}))


def read_supplement(symbol: str) -> pd.DataFrame:
    manifest = read_json(HERE / "source_supplement_manifest.json")
    item = next(value for value in manifest["items"] if value["symbol"] == symbol)
    raw = Path(item["path"]).read_bytes()
    if len(raw) != int(item["bytes"]) or sha256_bytes(raw) != item["sha256"]:
        raise RuntimeError(f"supplement identity mismatch: {symbol}")
    frame = pd.DataFrame(json.loads(raw), columns=[
        "open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume",
        "trade_count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
    ])
    frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    for column in ("open", "high", "low", "close", "volume", "quote_volume"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    return frame.set_index("open_time").sort_index()


def load_all() -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    parent = load_parent_module()
    bars: dict[str, pd.DataFrame] = {}
    funding: dict[str, pd.DataFrame] = {}
    for symbol in SYMBOLS:
        recent, funding[symbol] = parent.load_symbol("development", symbol)
        early = read_supplement(symbol)
        combined = pd.concat([early, recent], axis=0).sort_index()
        combined = combined[~combined.index.duplicated(keep="last")]
        bars[symbol] = combined
    return bars, funding


def ema_paper(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(alpha=1.0 / (1.0 + length), adjust=False, min_periods=length).mean()


def compute_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    close, high, low, volume = frame["close"], frame["high"], frame["low"], frame["quote_volume"]
    output = pd.DataFrame(index=frame.index)
    change = close.diff()
    gain = change.clip(lower=0.0).rolling(14, min_periods=14).mean()
    loss = (-change.clip(upper=0.0)).rolling(14, min_periods=14).mean()
    rs = gain / loss.replace(0.0, np.nan)
    output["rsi14"] = 100.0 - 100.0 / (1.0 + rs)
    output.loc[(loss == 0.0) & (gain > 0.0), "rsi14"] = 100.0
    output.loc[(loss == 0.0) & (gain == 0.0), "rsi14"] = 50.0
    rsi_min, rsi_max = output["rsi14"].rolling(14).min(), output["rsi14"].rolling(14).max()
    rsi_range = rsi_max - rsi_min
    output["stoch_rsi14"] = (output["rsi14"] - rsi_min) / rsi_range.replace(0.0, np.nan)
    output.loc[rsi_range == 0.0, "stoch_rsi14"] = 0.5
    low14, high14 = low.rolling(14).min(), high.rolling(14).max()
    output["stoch_k14"] = (close - low14) / (high14 - low14)
    output["stoch_d3"] = output["stoch_k14"].rolling(3).mean()
    typical = (close + high + low) / 3.0
    typical_mean = typical.rolling(20).mean()
    mean_dev = typical.rolling(20).apply(lambda values: float(np.mean(np.abs(values - np.mean(values)))), raw=True)
    output["cci20"] = (typical - typical_mean) / (0.015 * mean_dev)
    for length in (3, 5, 10, 20, 50, 100, 200):
        output[f"sma_{length}"] = close.rolling(length).mean() / close
    ema12, ema26 = ema_paper(close, 12), ema_paper(close, 26)
    output["macd"] = (ema12 - ema26) / ema12
    output["macd_diff"] = output["macd"] - ema_paper(output["macd"], 9)
    for length in (3, 5, 10, 20, 50, 100, 200):
        output[f"volsma_{length}"] = volume.rolling(length).mean() / volume.replace(0.0, np.nan)
    vema12, vema26 = ema_paper(volume, 12), ema_paper(volume, 26)
    output["volmacd"] = (vema12 - vema26) / vema12
    output["volmacd_diff"] = output["volmacd"] - ema_paper(output["volmacd"], 9)
    multiplier = ((close - low) - (high - close)) / (high - low).replace(0.0, np.nan)
    ad = multiplier * volume
    output["chaikin21"] = ad.rolling(21).sum() / volume.rolling(21).sum()
    middle = close.rolling(20).mean()
    sigma = close.rolling(20).std(ddof=0)
    output["boll_low"] = (middle - 2.0 * sigma) / close
    output["boll_mid"] = middle / close
    output["boll_high"] = (middle + 2.0 * sigma) / close
    output["boll_width"] = (4.0 * sigma) / middle
    output["mom21"] = close / close.shift(21) - 1.0
    output["sma20_trend"] = close / middle - 1.0
    output["median_quote_volume_30d"] = volume.rolling(30).median()
    return output.replace([np.inf, -np.inf], np.nan)


def rank_to_unit(values: pd.Series) -> pd.Series:
    if len(values) < 2:
        return pd.Series(np.nan, index=values.index)
    return (values.rank(method="average") - 1.0) / (len(values) - 1.0) - 0.5


def build_weekly_panel(bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
    indicators = {symbol: compute_indicators(frame) for symbol, frame in bars.items()}
    rows: list[dict[str, Any]] = []
    for entry in pd.date_range("2021-01-04T00:00:00Z", "2024-01-01T00:00:00Z", freq="W-MON"):
        decision = entry - pd.Timedelta(days=1)
        exit_time = entry + pd.Timedelta(days=7)
        candidates: list[dict[str, Any]] = []
        for symbol in SYMBOLS:
            if decision not in indicators[symbol].index or entry not in bars[symbol].index or exit_time not in bars[symbol].index:
                continue
            feature_row = indicators[symbol].loc[decision]
            if feature_row[FEATURES + ["mom21", "sma20_trend", "median_quote_volume_30d"]].isna().any():
                continue
            if float(feature_row["median_quote_volume_30d"]) < float(CONFIG["minimum_median_quote_volume_30d"]):
                continue
            candidates.append({
                "entry_time": entry, "decision_time": decision, "exit_time": exit_time, "symbol": symbol,
                "entry_price": float(bars[symbol].at[entry, "open"]), "exit_price": float(bars[symbol].at[exit_time, "open"]),
                "future_return": float(bars[symbol].at[exit_time, "open"] / bars[symbol].at[entry, "open"] - 1.0),
                "weight_proxy": float(feature_row["median_quote_volume_30d"]),
                "mom21": float(feature_row["mom21"]), "sma20_trend": float(feature_row["sma20_trend"]),
                **{name: float(feature_row[name]) for name in FEATURES},
            })
        if len(candidates) < int(CONFIG["minimum_rankable_symbols"]):
            continue
        week = pd.DataFrame(candidates).set_index("symbol")
        for name in FEATURES:
            week[name] = rank_to_unit(week[name])
        lower, upper = week["weight_proxy"].quantile([0.05, 0.95])
        week["model_weight"] = week["weight_proxy"].clip(lower=lower, upper=upper)
        week["model_weight"] /= week["model_weight"].sum()
        week["eligible_count"] = len(week)
        rows.extend(week.reset_index().to_dict("records"))
    if not rows:
        raise RuntimeError("weekly panel is empty")
    return pd.DataFrame(rows).sort_values(["entry_time", "symbol"]).reset_index(drop=True)


def weighted_univariate(frame: pd.DataFrame, feature: str) -> tuple[float, float]:
    x = frame[feature].to_numpy(float)
    y = frame["future_return"].to_numpy(float)
    w = frame["model_weight"].to_numpy(float)
    design = np.column_stack([np.ones(len(frame)), x])
    root = np.sqrt(w)
    coefficients, *_ = np.linalg.lstsq(design * root[:, None], y * root, rcond=None)
    return float(coefficients[0]), float(coefficients[1])


def select_elastic_net(x: np.ndarray, y: np.ndarray, weights: np.ndarray) -> tuple[ElasticNet, float, float]:
    best: tuple[float, ElasticNet, float] | None = None
    normalized = weights / np.mean(weights)
    n = len(y)
    for alpha in CONFIG["elastic_net_alpha_grid"]:
        model = ElasticNet(alpha=float(alpha), l1_ratio=float(CONFIG["elastic_net_l1_ratio"]), fit_intercept=True,
                           max_iter=50_000, tol=1e-9, selection="cyclic")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", ConvergenceWarning)
                model.fit(x, y, sample_weight=normalized)
        except ConvergenceWarning:
            continue
        residual = y - model.predict(x)
        rss = max(float(np.sum(normalized * residual * residual)), np.finfo(float).tiny)
        k = int(np.count_nonzero(np.abs(model.coef_) > 1e-12)) + 1
        if n <= k + 1:
            continue
        aicc = n * math.log(rss / n) + 2.0 * k + 2.0 * k * (k + 1.0) / (n - k - 1.0)
        if best is None or aicc < best[0]:
            best = (aicc, model, float(alpha))
    if best is None:
        raise RuntimeError("elastic net AICc selection produced no valid model")
    return best[1], best[2], best[0]


def fit_week_score(panel: pd.DataFrame, target_week: pd.Timestamp, training_weeks: int,
                   feature_names: list[str], combination: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    available = sorted(pd.Timestamp(value) for value in panel.loc[panel["entry_time"] < target_week, "entry_time"].unique())
    if len(available) < training_weeks:
        raise RuntimeError(f"insufficient training weeks: {len(available)} < {training_weeks}")
    chosen = available[-training_weeks:]
    train = panel[panel["entry_time"].isin(chosen)].copy()
    target = panel[panel["entry_time"] == target_week].copy()
    if target.empty:
        raise RuntimeError("target week has no eligible cross section")
    train_predictions = np.empty((len(train), len(feature_names)))
    target_predictions = np.empty((len(target), len(feature_names)))
    coefficients: dict[str, list[float]] = {}
    for column_index, feature in enumerate(feature_names):
        weekly_coefficients = [weighted_univariate(train[train["entry_time"] == week], feature) for week in chosen]
        intercept = float(np.mean([value[0] for value in weekly_coefficients]))
        slope = float(np.mean([value[1] for value in weekly_coefficients]))
        coefficients[feature] = [intercept, slope]
        train_predictions[:, column_index] = intercept + slope * train[feature].to_numpy(float)
        target_predictions[:, column_index] = intercept + slope * target[feature].to_numpy(float)
    if combination == "naive_all":
        selected = list(range(len(feature_names)))
        alpha, aicc, enet_coefficients = None, None, [1.0] * len(feature_names)
    else:
        model, alpha, aicc = select_elastic_net(
            train_predictions, train["future_return"].to_numpy(float), train["model_weight"].to_numpy(float)
        )
        selected = [index for index, value in enumerate(model.coef_) if value > 1e-12]
        enet_coefficients = [float(value) for value in model.coef_]
        if not selected:
            raise RuntimeError("elastic net selected no positive component forecast")
    target["score"] = target_predictions[:, selected].mean(axis=1)
    metadata = {
        "target_week": target_week.isoformat(), "training_weeks": training_weeks,
        "training_start": chosen[0].isoformat(), "training_end": chosen[-1].isoformat(),
        "training_rows": int(len(train)), "eligible_symbols": int(len(target)),
        "combination": combination, "alpha": alpha, "aicc": aicc,
        "selected_features": [feature_names[index] for index in selected],
        "elastic_net_coefficients": dict(zip(feature_names, enet_coefficients, strict=True)),
        "mean_univariate_coefficients": coefficients,
    }
    return target, metadata


def score_stage(panel: pd.DataFrame, stage: str, *, training_weeks: int, feature_names: list[str],
                combination: str) -> tuple[dict[pd.Timestamp, pd.DataFrame], list[dict[str, Any]]]:
    start, end = map(pd.Timestamp, STAGES[stage])
    scores: dict[pd.Timestamp, pd.DataFrame] = {}
    metadata: list[dict[str, Any]] = []
    for week in pd.date_range(start, end, freq="W-MON", inclusive="left"):
        try:
            score, info = fit_week_score(panel, week, training_weeks, feature_names, combination)
            scores[week] = score
            metadata.append({"status": "PASS", **info})
        except Exception as exc:
            metadata.append({"target_week": week.isoformat(), "status": "FAIL", "error": f"{type(exc).__name__}: {exc}"})
    return scores, metadata


def stressed_long_rate(rate: float) -> float:
    if rate > 0:
        return rate * float(CONFIG["long_funding_stress"]["positive_cost_multiplier"])
    return rate * float(CONFIG["long_funding_stress"]["negative_benefit_multiplier"])


def make_trades(scores: dict[pd.Timestamp, pd.DataFrame], funding: dict[str, pd.DataFrame], stage: str,
                name: str, *, mode: str = "top", cooldown: bool = True) -> tuple[pd.DataFrame, dict[str, int]]:
    rows: list[dict[str, Any]] = []
    last_exit: dict[str, pd.Timestamp] = {}
    planned = excluded_marks = cooldown_skips = 0
    for entry in sorted(scores):
        week = scores[entry].copy()
        if mode == "top":
            count = int(math.ceil(len(week) * float(CONFIG["top_fraction"])))
            week = week.sort_values(["score", "symbol"], ascending=[False, True]).head(count)
        elif mode == "all":
            week = week.sort_values("symbol")
        else:
            raise ValueError(mode)
        for rank, (_, item) in enumerate(week.iterrows(), start=1):
            symbol = str(item["symbol"])
            planned += 1
            if cooldown and symbol in last_exit and entry <= last_exit[symbol] + pd.Timedelta(days=int(CONFIG["cooldown_full_days"])):
                cooldown_skips += 1
                continue
            exit_time = pd.Timestamp(item["exit_time"])
            rates = funding[symbol][(funding[symbol].index > entry) & (funding[symbol].index <= exit_time)]
            if rates["markPrice"].isna().any():
                excluded_marks += 1
                last_exit[symbol] = exit_time
                continue
            entry_price, exit_price = float(item["entry_price"]), float(item["exit_price"])
            fraction = float(CONFIG["notional_fraction"])
            quantity = fraction / entry_price
            actual_funding = -float((quantity * rates["markPrice"] * rates["fundingRate"]).sum())
            stress_funding = -float((quantity * rates["markPrice"] * rates["fundingRate"].map(stressed_long_rate)).sum())
            rows.append({
                "trade_id": f"{stage}-{name}-{entry:%Y%m%d}-{symbol}", "strategy_variant": name,
                "entry_time": entry, "exit_time": exit_time, "decision_time": item["decision_time"], "symbol": symbol,
                "score": float(item.get("score", np.nan)), "selection_rank": rank, "eligible_count": int(item["eligible_count"]),
                "entry_price": entry_price, "exit_price": exit_price, "notional_fraction": fraction,
                "quantity_per_unit_plan_capital": quantity, "funding_events": int(len(rates)),
                "actual_funding_return": actual_funding, "stress_funding_return": stress_funding,
                "gross_long_return": fraction * (exit_price / entry_price - 1.0),
            })
            last_exit[symbol] = exit_time
    return pd.DataFrame(rows), {"planned": planned, "excluded_missing_marks": excluded_marks, "cooldown_skips": cooldown_skips}


def simple_scores(panel: pd.DataFrame, stage: str, column: str) -> dict[pd.Timestamp, pd.DataFrame]:
    start, end = map(pd.Timestamp, STAGES[stage])
    result: dict[pd.Timestamp, pd.DataFrame] = {}
    for entry in pd.date_range(start, end, freq="W-MON", inclusive="left"):
        week = panel[panel["entry_time"] == entry].copy()
        if week.empty:
            continue
        week["score"] = week[column]
        result[entry] = week
    return result


def vectorbt_long_returns(trades: pd.DataFrame, fee: float, slippage: float) -> np.ndarray:
    columns = trades["trade_id"].tolist()
    prices = pd.DataFrame([trades["entry_price"].to_numpy(float), trades["exit_price"].to_numpy(float)], columns=columns)
    quantity = trades["quantity_per_unit_plan_capital"].to_numpy(float)
    sizes = pd.DataFrame([quantity, -quantity], columns=columns)
    portfolio = vbt.Portfolio.from_orders(
        prices, size=sizes, size_type="amount", direction="both", fees=fee, slippage=slippage,
        init_cash=1.0, freq="1D",
    )
    return portfolio.total_return().reindex(columns).to_numpy(float)


def manual_long_return(row: pd.Series, fee: float, slippage: float) -> float:
    quantity = float(row["quantity_per_unit_plan_capital"])
    entry_execution = float(row["entry_price"]) * (1.0 + slippage)
    exit_execution = float(row["exit_price"]) * (1.0 - slippage)
    return quantity * (exit_execution - entry_execution) - quantity * entry_execution * fee - quantity * exit_execution * fee


def attach_returns(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        raise RuntimeError("strategy produced no trades")
    output = trades.copy()
    for scenario, assumptions in CONFIG["costs"].items():
        vbt_return = vectorbt_long_returns(output, float(assumptions["fee_per_side"]), float(assumptions["slippage_per_side"]))
        manual = output.apply(manual_long_return, axis=1, fee=float(assumptions["fee_per_side"]),
                              slippage=float(assumptions["slippage_per_side"])).to_numpy(float)
        output[f"{scenario}_price_cost_return"] = vbt_return
        output[f"{scenario}_reconciliation_error"] = vbt_return - manual
        funding_column = "stress_funding_return" if assumptions["funding_stress"] else "actual_funding_return"
        output[f"{scenario}_net_return"] = vbt_return + output[funding_column].to_numpy(float)
    return output


def date_returns(trades: pd.DataFrame, column: str) -> pd.Series:
    return trades.groupby("entry_time")[column].mean().sort_index()


def hurdle_per_week() -> float:
    return float(CONFIG["annual_capital_hurdle"]) * float(CONFIG["hold_days"]) / 365.0


def block_bootstrap_mean_ci(values: np.ndarray) -> list[float]:
    values = np.asarray(values, dtype=float)
    block = int(CONFIG["bootstrap"]["block_weeks"])
    reps = int(CONFIG["bootstrap"]["repetitions"])
    rng = np.random.default_rng(int(CONFIG["bootstrap"]["seed"]))
    means = np.empty(reps)
    for index in range(reps):
        chosen: list[int] = []
        while len(chosen) < len(values):
            start = int(rng.integers(0, len(values)))
            chosen.extend(((start + np.arange(block)) % len(values)).tolist())
        means[index] = float(values[np.asarray(chosen[:len(values)])].mean())
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def max_drawdown(returns: pd.Series) -> float:
    equity = (1.0 + returns).cumprod()
    return float((equity / equity.cummax().clip(lower=1.0) - 1.0).min())


def summarize(trades: pd.DataFrame, stage: str, categories: dict[str, str], model_metadata: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    start, end = map(pd.Timestamp, STAGES[stage])
    result: dict[str, Any] = {
        "trades": int(len(trades)), "entry_dates": int(trades["entry_time"].nunique()),
        "symbols": int(trades["symbol"].nunique()), "funding_events": int(trades["funding_events"].sum()),
        "maximum_vectorbt_reconciliation_error": float(max(trades[f"{name}_reconciliation_error"].abs().max() for name in CONFIG["costs"])),
        "scenarios": {}, "by_half": {}, "by_symbol": {}, "by_category": {},
    }
    for scenario in CONFIG["costs"]:
        weekly = date_returns(trades, f"{scenario}_net_return")
        adjusted = weekly - hurdle_per_week()
        total = float(np.prod(1.0 + weekly.to_numpy(float)) - 1.0)
        result["scenarios"][scenario] = {
            "date_mean": float(weekly.mean()), "date_mean_after_hurdle": float(adjusted.mean()),
            "date_mean_after_hurdle_bootstrap_95pct": block_bootstrap_mean_ci(adjusted.to_numpy(float)),
            "compound_return": total,
            "annualized_return": float((1.0 + total) ** (365.0 / (end - start).days) - 1.0),
            "date_portfolio_max_drawdown": max_drawdown(weekly),
        }
    base_adjusted = date_returns(trades, "base_net_return") - hurdle_per_week()
    midpoint = start + (end - start) / 2
    for label, mask in (("H1", base_adjusted.index < midpoint), ("H2", base_adjusted.index >= midpoint)):
        values = base_adjusted[mask]
        result["by_half"][label] = {"dates": int(len(values)), "mean_after_hurdle": float(values.mean())}
    target_means: dict[str, float] = {}
    target_drawdowns: dict[str, float] = {}
    for symbol, group in trades.groupby("symbol"):
        series = group.sort_values("entry_time")["base_net_return"]
        target_means[str(symbol)] = float((series - hurdle_per_week()).mean())
        target_drawdowns[str(symbol)] = max_drawdown(series)
    result["by_symbol"] = {
        symbol: {"trades": int((trades["symbol"] == symbol).sum()), "base_mean_after_hurdle": target_means[symbol],
                 "base_max_drawdown": target_drawdowns[symbol]}
        for symbol in sorted(target_means)
    }
    result["worst_symbol_base_max_drawdown"] = float(min(target_drawdowns.values()))
    pnl = trades.groupby("symbol")["base_net_return"].sum()
    positive = pnl.clip(lower=0.0)
    result["largest_positive_pnl_share"] = float(positive.max() / positive.sum()) if positive.sum() > 0 else 1.0
    for category in sorted(set(categories.values())):
        category_symbols = [symbol for symbol, value in categories.items() if value == category]
        subset = trades[trades["symbol"].isin(category_symbols)]
        if not subset.empty:
            result["by_category"][category] = {
                "trades": int(len(subset)), "base_mean_after_hurdle": float((subset["base_net_return"] - hurdle_per_week()).mean())
            }
    if model_metadata is not None:
        passed = [item for item in model_metadata if item["status"] == "PASS"]
        failed = [item for item in model_metadata if item["status"] == "FAIL"]
        selected_counts = [len(item["selected_features"]) for item in passed]
        frequencies = {feature: sum(feature in item["selected_features"] for item in passed) for feature in FEATURES}
        result["model"] = {
            "weeks_passed": len(passed), "weeks_failed": len(failed),
            "failure_fraction": len(failed) / max(1, len(model_metadata)),
            "median_selected_features": float(np.median(selected_counts)) if selected_counts else 0.0,
            "selection_frequency": frequencies,
            "failures": failed,
        }
    return result


def compare(main: pd.DataFrame, baseline: pd.DataFrame, column: str = "base_net_return") -> dict[str, Any]:
    left = date_returns(main, column)
    right = date_returns(baseline, column).reindex(left.index)
    if right.isna().any():
        raise RuntimeError("baseline missing a main entry date")
    difference = left - right
    return {
        "main_mean": float(left.mean()), "baseline_mean": float(right.mean()), "difference_mean": float(difference.mean()),
        "difference_bootstrap_95pct": block_bootstrap_mean_ci(difference.to_numpy(float)),
        "positive_date_fraction": float((difference > 0).mean()),
    }


def command_self_test(_args: argparse.Namespace) -> None:
    index = pd.date_range("2020-01-01", periods=260, freq="1D", tz="UTC")
    price = pd.Series(np.exp(np.linspace(0.0, 0.3, len(index))) * (1.0 + 0.01 * np.sin(np.arange(len(index)) / 5)), index=index)
    frame = pd.DataFrame({"open": price, "high": price * 1.01, "low": price * 0.99, "close": price,
                          "quote_volume": np.linspace(1e7, 2e7, len(index))}, index=index)
    features = compute_indicators(frame)
    assert features[FEATURES].iloc[-1].notna().all() and len(FEATURES) == 28
    sample_x = np.linspace(-0.5, 0.5, 30)
    sample = pd.DataFrame({"future_return": 0.01 + 0.03 * sample_x + 0.002 * np.sin(np.arange(30)),
                           "model_weight": np.linspace(0.5, 1.5, 30), "x": sample_x})
    intercept, slope = weighted_univariate(sample, "x")
    assert math.isfinite(intercept) and math.isfinite(slope)
    x = np.column_stack([sample["x"], -sample["x"]])
    model, alpha, aicc = select_elastic_net(x, sample["future_return"].to_numpy(), sample["model_weight"].to_numpy())
    assert math.isfinite(alpha) and math.isfinite(aicc) and len(model.coef_) == 2
    print(json.dumps({"status": "PASS", "features": len(FEATURES), "alpha_grid": len(CONFIG["elastic_net_alpha_grid"])}))


def stage_authorized(stage: str) -> None:
    prior = {"evaluation": "development", "confirmation": "evaluation"}.get(stage)
    if prior is not None:
        gate_path = HERE / f"{prior}_gate.json"
        if not gate_path.exists() or read_json(gate_path).get("status") != "PASS":
            raise RuntimeError(f"{stage} is sealed until {prior} PASS")


def command_analyze(args: argparse.Namespace) -> None:
    ensure_checkpoint()
    stage_authorized(args.stage)
    if args.stage != "development":
        raise RuntimeError("later-stage retrieval has not been authorized or prepared")
    dq = read_json(HERE / "data_quality_development.json")
    if dq["status"] != "PASS":
        raise RuntimeError("data quality is not PASS")
    bars, funding = load_all()
    panel = build_weekly_panel(bars)
    categories = category_map()
    main_scores, main_model = score_stage(panel, args.stage, training_weeks=52, feature_names=FEATURES, combination="elastic_net")
    score_sets: dict[str, dict[pd.Timestamp, pd.DataFrame]] = {"main": main_scores}
    model_sets: dict[str, list[dict[str, Any]]] = {"main": main_model}
    for name, config in CONFIG["diagnostics"].items():
        features = FEATURES if config["features"] == "all" else NON_VOLUME_FEATURES
        score_sets[name], model_sets[name] = score_stage(
            panel, args.stage, training_weeks=int(config["training_weeks"]), feature_names=features,
            combination=str(config["combination"]),
        )
    score_sets["mom21"] = simple_scores(panel, args.stage, "mom21")
    score_sets["sma20"] = simple_scores(panel, args.stage, "sma20_trend")
    score_sets["scheduled_long"] = simple_scores(panel, args.stage, "mom21")
    score_sets["market"] = simple_scores(panel, args.stage, "mom21")
    trades: dict[str, pd.DataFrame] = {}
    opportunity_counts: dict[str, dict[str, int]] = {}
    for name in ("main", "window26", "window78", "no_volume", "naive_all", "mom21", "sma20"):
        raw, opportunity_counts[name] = make_trades(score_sets[name], funding, args.stage, name, mode="top", cooldown=True)
        trades[name] = attach_returns(raw)
    for name, cooldown in (("scheduled_long", True), ("market", False)):
        raw, opportunity_counts[name] = make_trades(score_sets[name], funding, args.stage, name, mode="all", cooldown=cooldown)
        trades[name] = attach_returns(raw)
    csv_hashes: dict[str, str] = {}
    for name, frame in trades.items():
        path = HERE / f"{args.stage}_{name}_trades.csv"
        frame.to_csv(path, index=False, date_format="%Y-%m-%dT%H:%M:%S%z")
        csv_hashes[path.name] = sha256_file(path)
    summaries = {
        name: summarize(frame, args.stage, categories, model_sets.get(name))
        for name, frame in trades.items()
    }
    gross_main = date_returns(trades["main"], "gross_long_return")
    gross_market = date_returns(trades["market"], "gross_long_return").reindex(gross_main.index)
    gross_excess = gross_main - gross_market
    comparisons = {
        "base_vs_mom21": compare(trades["main"], trades["mom21"]),
        "base_vs_sma20": compare(trades["main"], trades["sma20"]),
        "base_vs_scheduled_long": compare(trades["main"], trades["scheduled_long"]),
        "gross_vs_equal_weight_market": {
            "main_mean": float(gross_main.mean()), "market_mean": float(gross_market.mean()),
            "difference_mean": float(gross_excess.mean()),
            "difference_bootstrap_95pct": block_bootstrap_mean_ci(gross_excess.to_numpy(float)),
        },
    }
    payload = {
        "created_at_utc": iso_now(), "stage": args.stage,
        "checkpoint_digest": read_json(HERE / "checkpoint.json")["content_digest"],
        "data_quality_digest": dq["content_digest"], "panel_rows": int(len(panel)),
        "panel_weeks": int(panel["entry_time"].nunique()), "opportunity_counts": opportunity_counts,
        "summaries": summaries, "comparisons": comparisons, "model_metadata": model_sets,
        "trade_csv_sha256": csv_hashes,
    }
    write_json(HERE / f"{args.stage}.json", payload, digest=True)
    output = read_json(HERE / f"{args.stage}.json")
    print(json.dumps({"stage": args.stage, "trades": summaries["main"]["trades"],
                      "base_after_hurdle": summaries["main"]["scenarios"]["base"]["date_mean_after_hurdle"],
                      "stress_after_hurdle": summaries["main"]["scenarios"]["stress"]["date_mean_after_hurdle"],
                      "digest": output["content_digest"]}))


def command_gate(args: argparse.Namespace) -> None:
    ensure_checkpoint()
    stage_authorized(args.stage)
    evidence = read_json(HERE / f"{args.stage}.json")
    main = evidence["summaries"]["main"]
    opportunities = evidence["opportunity_counts"]["main"]
    eligible_targets = [value for value in main["by_symbol"].values() if value["trades"] >= 5]
    positive_targets = [value for value in eligible_targets if value["base_mean_after_hurdle"] > 0]
    positive_categories = [value for value in main["by_category"].values() if value["base_mean_after_hurdle"] > 0]
    neighbors = [evidence["summaries"][name]["scenarios"]["stress"]["date_mean_after_hurdle"] >= 0
                 for name in ("window26", "window78", "no_volume")]
    checks = {
        "data_quality_pass": read_json(HERE / "data_quality_development.json")["status"] == "PASS",
        "minimum_150_trades": main["trades"] >= 150,
        "minimum_20_symbols": main["symbols"] >= 20,
        "minimum_45_entry_dates": main["entry_dates"] >= 45,
        "excluded_missing_marks_at_most_2pct": opportunities["excluded_missing_marks"] / max(1, opportunities["planned"]) <= 0.02,
        "model_failure_fraction_at_most_5pct": main["model"]["failure_fraction"] <= 0.05,
        "median_at_least_5_selected_features": main["model"]["median_selected_features"] >= 5,
        "base_after_hurdle_positive": main["scenarios"]["base"]["date_mean_after_hurdle"] > 0,
        "stress_after_hurdle_positive": main["scenarios"]["stress"]["date_mean_after_hurdle"] > 0,
        "stress_bootstrap_lower_positive": main["scenarios"]["stress"]["date_mean_after_hurdle_bootstrap_95pct"][0] > 0,
        "both_halves_base_positive": all(value["mean_after_hurdle"] > 0 for value in main["by_half"].values()),
        "date_portfolio_drawdown_above_minus_20pct": main["scenarios"]["base"]["date_portfolio_max_drawdown"] > -0.20,
        "worst_symbol_drawdown_above_minus_45pct": main["worst_symbol_base_max_drawdown"] > -0.45,
        "base_beats_mom21": evidence["comparisons"]["base_vs_mom21"]["difference_mean"] > 0,
        "base_beats_sma20": evidence["comparisons"]["base_vs_sma20"]["difference_mean"] > 0,
        "base_beats_scheduled_long": evidence["comparisons"]["base_vs_scheduled_long"]["difference_mean"] > 0,
        "gross_excess_vs_market_positive": evidence["comparisons"]["gross_vs_equal_weight_market"]["difference_mean"] > 0,
        "gross_excess_bootstrap_lower_positive": evidence["comparisons"]["gross_vs_equal_weight_market"]["difference_bootstrap_95pct"][0] > 0,
        "at_least_two_of_three_neighbors_stress_nonnegative": sum(neighbors) >= 2,
        "at_least_half_eligible_targets_positive": len(eligible_targets) > 0 and len(positive_targets) / len(eligible_targets) >= 0.5,
        "at_least_four_categories_positive": len(positive_categories) >= 4,
        "largest_positive_pnl_share_at_most_20pct": main["largest_positive_pnl_share"] <= 0.20,
        "vectorbt_manual_reconciliation": main["maximum_vectorbt_reconciliation_error"] <= 1e-10,
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    gate = {"created_at_utc": iso_now(), "stage": args.stage, "status": status, "checks": checks,
            "failed": [name for name, passed in checks.items() if not passed], "evidence_digest": evidence["content_digest"]}
    write_json(HERE / f"{args.stage}_gate.json", gate, digest=True)
    if status == "FAIL":
        base = main["scenarios"]["base"]["date_mean_after_hurdle"]
        stress = main["scenarios"]["stress"]["date_mean_after_hurdle"]
        conclusion = "DOES_NOT_SUPPORT" if base <= 0 or stress <= 0 else "INSUFFICIENT_EVIDENCE"
        results = {
            "created_at_utc": iso_now(), "question": read_json(HERE / "checkpoint.json")["question"],
            "conclusion": conclusion, "development_gate": "FAIL", "development_digest": evidence["content_digest"],
            "gate_digest": read_json(HERE / f"{args.stage}_gate.json")["content_digest"],
            "later_stage_outputs": 0, "handoff_generated": False,
            "summary": {
                "trades": main["trades"], "entry_dates": main["entry_dates"], "symbols": main["symbols"],
                "base_mean_after_hurdle": base, "stress_mean_after_hurdle": stress,
                "stress_bootstrap_95pct": main["scenarios"]["stress"]["date_mean_after_hurdle_bootstrap_95pct"],
                "base_max_drawdown": main["scenarios"]["base"]["date_portfolio_max_drawdown"],
                "gross_excess_vs_market": evidence["comparisons"]["gross_vs_equal_weight_market"],
                "model": main["model"], "failed_checks": gate["failed"],
            },
        }
        write_json(HERE / "results.json", results, digest=True)
        result = read_json(HERE / "results.json")
        narrative = f"""# 结果：CTREND 单腿 one-shot 转换未通过开发门

## 结论

`{conclusion}`

固定的 28 信号、52 周 CS-C-ENet、顶部五分位、`0.5x LONG / 7d` 转换在 2023 development 没有通过全部现实成本、统计、基准、稳健性、广度与风险门。它不进入 evaluation/confirmation，不生成交易核心 handoff，也不修改正式策略、产品代码、资金或真实账户。

## 关键数值

- 交易 / entry dates / 目标：`{main['trades']} / {main['entry_dates']} / {main['symbols']}`。
- base / stress 扣 4% 全计划资本周门槛均值：`{base:.6%} / {stress:.6%}`。
- stress 四周 block-bootstrap 95% 区间：`[{main['scenarios']['stress']['date_mean_after_hurdle_bootstrap_95pct'][0]:.6%}, {main['scenarios']['stress']['date_mean_after_hurdle_bootstrap_95pct'][1]:.6%}]`。
- base date-portfolio 最大回撤：`{main['scenarios']['base']['date_portfolio_max_drawdown']:.6%}`。
- gross 相对同周等权市场均值：`{evidence['comparisons']['gross_vs_equal_weight_market']['difference_mean']:.6%}`；95% 区间 `[{evidence['comparisons']['gross_vs_equal_weight_market']['difference_bootstrap_95pct'][0]:.6%}, {evidence['comparisons']['gross_vs_equal_weight_market']['difference_bootstrap_95pct'][1]:.6%}]`。
- 每周入选特征中位数：`{main['model']['median_selected_features']:.1f}`；模型失败比例 `{main['model']['failure_fraction']:.3%}`。
- 失败门：`{', '.join(gate['failed'])}`。

## 解释边界

本结果只判断 Halpha 的当前幸存永续、成交额代理权重、固定单目标、零售成本和 one-shot 转换；不推翻原论文的全市场、多币、市值加权 long-short 因子。正收益也不会证明长期 Alpha；如果主要收益能由 MOM21、单均线或市场 beta 解释，就没有相对正式 Donchian 的独立项目价值。

evaluation 和 confirmation 未打开。所有模型元数据、交易 CSV、数据身份、失败门和尝试均保留，禁止从诊断中事后挑选新的主规则。
"""
        (HERE / "result.md").write_text(narrative, encoding="utf-8")
    print(json.dumps({"status": status, "failed": gate["failed"]}))


def command_validate(_args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    checked = 0
    for name in ("source_reuse_manifest.json", "source_supplement_manifest.json", "data_quality_development.json",
                 "development.json", "development_gate.json", "results.json"):
        path = HERE / name
        payload = read_json(path)
        digest = payload.pop("content_digest")
        if canonical_digest(payload) != digest:
            raise RuntimeError(f"canonical digest mismatch: {name}")
        checked += 1
    evidence = read_json(HERE / "development.json")
    for name, expected in evidence["trade_csv_sha256"].items():
        if sha256_file(HERE / name) != expected:
            raise RuntimeError(f"trade CSV hash mismatch: {name}")
    later = sum((HERE / name).exists() for name in ("evaluation.json", "confirmation.json", "handoff.json"))
    if later != 0:
        raise RuntimeError("later-stage artifact exists after development failure")
    result = read_json(HERE / "results.json")
    payload = {
        "validated_at_utc": iso_now(), "status": "PASS", "checkpoint_digest": checkpoint["content_digest"],
        "json_digest_files_checked": checked, "trade_csv_files_checked": len(evidence["trade_csv_sha256"]),
        "conclusion": result["conclusion"], "later_stage_outputs": later,
    }
    write_json(HERE / "validation.json", payload, digest=True)
    print(json.dumps(payload))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test").set_defaults(func=command_self_test)
    sub.add_parser("checkpoint").set_defaults(func=command_checkpoint)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--stage", choices=STAGES, default="development")
    prepare.set_defaults(func=command_prepare)
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--stage", choices=STAGES, default="development")
    analyze.set_defaults(func=command_analyze)
    gate = sub.add_parser("gate")
    gate.add_argument("--stage", choices=STAGES, default="development")
    gate.set_defaults(func=command_gate)
    sub.add_parser("validate").set_defaults(func=command_validate)
    return parser


if __name__ == "__main__":
    arguments = build_parser().parse_args()
    arguments.func(arguments)
