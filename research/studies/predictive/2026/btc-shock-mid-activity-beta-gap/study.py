from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
import vectorbt as vbt


STUDY_DIR = Path(__file__).resolve().parent
CHECKPOINT_PATH = STUDY_DIR / "checkpoint.json"
PARENT_DIR = STUDY_DIR.parent / "btc-shock-beta-gap-predictability"
PARENT_CODE = PARENT_DIR / "study.py"
EXPECTED_PARENT_CODE_SHA = "3c2d83c79881c81fdc08e9ea0e55a568ecd677c3809b0a86a1f8905fdfff1ea6"
RESEARCH_ROOT = STUDY_DIR.parents[3]
UNIVERSE_PATH = RESEARCH_ROOT / "market-universe" / "universe.csv"
EXPECTED_UNIVERSE_SHA = "1f24adfb64b7a52a170b730ee7517916b2da8ab45785779dee6be991762186cc"
DATA_ROOT = Path(
    "D:/projects/Codex/CodexHome/research-data/halpha/"
    "btc-shock-beta-gap-predictability"
)

MID_ALTS = [
    "BELUSDT",
    "ANKRUSDT",
    "JASMYUSDT",
    "ZENUSDT",
    "TRBUSDT",
    "MANAUSDT",
    "QTUMUSDT",
    "QNTUSDT",
    "ENJUSDT",
    "CFXUSDT",
    "EGLDUSDT",
    "IOTAUSDT",
]


def load_parent():
    name = "halpha_btc_gap_mid_parent"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, PARENT_CODE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {PARENT_CODE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


parent = load_parent()
ANCHOR = parent.ANCHOR
parent.ALTS = MID_ALTS
parent.SYMBOLS = [ANCHOR, *MID_ALTS]
SYMBOLS = list(parent.SYMBOLS)
PHASES = parent.PHASES


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def code_sha256() -> str:
    return sha256_path(Path(__file__))


def checkpoint() -> dict[str, Any]:
    return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))


def selected_universe() -> list[str]:
    frame = pd.read_csv(UNIVERSE_PATH, dtype=str, keep_default_na=False)
    age = pd.to_numeric(frame["age_days"], errors="coerce")
    spread = pd.to_numeric(frame["relative_spread_bps"], errors="coerce")
    activity = pd.to_numeric(
        frame["activity_notional_24h_usd_proxy"], errors="coerce"
    )
    mask = (
        frame["market"].eq("BINANCE_USD_M")
        & frame["currently_trading"].eq("True")
        & frame["contract_type"].eq("PERPETUAL")
        & frame["economic_exposure"].eq("CRYPTO_NATIVE")
        & frame["symbol"].str.endswith("USDT")
        & frame["research_bucket"].eq("CRYPTO_ALT_MID_ACTIVITY_PROVISIONAL")
        & age.ge(1100)
        & spread.le(3.5)
        & ~frame["risk_flags"].str.contains("OFFICIAL_MEME_SUBTYPE", regex=False)
        & ~frame["symbol"].str[0].str.isdigit()
        & ~frame["symbol"].eq("BTCDOMUSDT")
    )
    selected = frame.loc[mask].assign(_activity=activity.loc[mask])
    return selected.sort_values("_activity", ascending=False)["symbol"].head(12).tolist()


def verify_plan() -> None:
    plan = checkpoint()
    actual = code_sha256()
    failures: list[str] = []
    if sha256_path(PARENT_CODE) != EXPECTED_PARENT_CODE_SHA:
        failures.append("parent code changed")
    if sha256_path(UNIVERSE_PATH) != EXPECTED_UNIVERSE_SHA:
        failures.append("market universe snapshot changed")
    if selected_universe() != MID_ALTS:
        failures.append(f"selection rule now yields {selected_universe()}")
    if plan["symbols"] != MID_ALTS or plan["anchor"] != ANCHOR:
        failures.append("checkpoint symbols differ")
    if plan["parent_code_sha256"] != EXPECTED_PARENT_CODE_SHA:
        failures.append("checkpoint parent hash differs")
    expected = plan["study_code_sha256"]
    if expected == "PENDING_BEFORE_FIRST_DOWNLOAD":
        failures.append(f"checkpoint code hash pending; actual={actual}")
    elif expected != actual:
        failures.append(f"code hash mismatch: checkpoint={expected}, actual={actual}")
    if failures:
        raise RuntimeError("; ".join(failures))
    print(
        json.dumps(
            {
                "status": "PASS",
                "study_code_sha256": actual,
                "parent_code_sha256": EXPECTED_PARENT_CODE_SHA,
                "universe_sha256": EXPECTED_UNIVERSE_SHA,
                "symbols": MID_ALTS,
                "pandas": pd.__version__,
                "numpy": np.__version__,
                "statsmodels": sm.__version__,
                "vectorbt": vbt.__version__,
            },
            indent=2,
        )
    )


def prior_phase_allows(phase: str) -> bool:
    if phase == "development":
        return True
    prior = "development" if phase == "evaluation" else "evaluation"
    path = STUDY_DIR / f"{prior}.json"
    if not path.exists():
        return False
    return bool(json.loads(path.read_text(encoding="utf-8")).get("release_next_phase"))


def prepare(phase: str, workers: int) -> None:
    verify_plan()
    if not prior_phase_allows(phase):
        raise RuntimeError(f"{phase} remains sealed by the prior phase result")
    tasks = [
        (symbol, month)
        for symbol in SYMBOLS
        for month in parent.phase_prepare_months(phase)
    ]
    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 4))) as executor:
        futures = {
            executor.submit(parent.prepare_one, symbol, month): (symbol, month)
            for symbol, month in tasks
        }
        for future in as_completed(futures):
            symbol, month = futures[future]
            try:
                records.append(future.result())
            except Exception as exc:
                failures.append(
                    {
                        "symbol": symbol,
                        "month": month.strftime("%Y-%m"),
                        "error": repr(exc),
                    }
                )
            completed = len(records) + len(failures)
            if completed % 25 == 0 or completed == len(tasks):
                print(f"prepare {phase}: {completed}/{len(tasks)}")
    manifest = {
        "phase": phase,
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "source": "Binance official USD-M monthly 5m Kline archive",
        "shared_cache": DATA_ROOT.as_posix(),
        "study_code_sha256": code_sha256(),
        "parent_downloader_sha256": EXPECTED_PARENT_CODE_SHA,
        "selection_rule": checkpoint()["selection_rule"],
        "file_count": len(records),
        "total_bytes": sum(item["bytes"] for item in records),
        "failures": sorted(failures, key=lambda item: (item["symbol"], item["month"])),
        "files": sorted(records, key=lambda item: (item["symbol"], item["month"])),
    }
    path = STUDY_DIR / f"source_manifest_{phase}.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if failures:
        raise RuntimeError(f"{len(failures)} sources failed; inspect {path.name}")
    print(json.dumps({"status": "PASS", "files": len(records), "manifest": str(path)}))


def validate_sources(phase: str) -> dict[str, Any]:
    phase_order = ["development"]
    if phase in {"evaluation", "confirmation"}:
        phase_order.append("evaluation")
    if phase == "confirmation":
        phase_order.append("confirmation")
    identities: list[dict[str, Any]] = []
    total_files = 0
    total_bytes = 0
    for item_phase in phase_order:
        path = STUDY_DIR / f"source_manifest_{item_phase}.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for item in manifest["files"]:
            local = DATA_ROOT / item["cache_relative_path"]
            actual = sha256_path(local)
            if actual != item["actual_sha256"] or actual != item["official_sha256"]:
                raise ValueError(f"source hash mismatch: {local}")
            if local.stat().st_size != item["bytes"]:
                raise ValueError(f"source size mismatch: {local}")
            total_files += 1
            total_bytes += item["bytes"]
        identities.append(
            {
                "path": path.name,
                "sha256": sha256_path(path),
                "file_count": len(manifest["files"]),
            }
        )
    return {
        "status": "PASS",
        "manifests": identities,
        "validated_file_count": total_files,
        "validated_zip_bytes": total_bytes,
        "shared_cache": DATA_ROOT.as_posix(),
    }


def run(phase: str) -> None:
    verify_plan()
    if not prior_phase_allows(phase):
        raise RuntimeError(f"{phase} remains sealed by the prior phase result")
    source_identity = validate_sources(phase)
    matrices, quality = parent.load_matrices(phase)
    returns = np.log(matrices["close"]).diff()
    btc_returns = returns[ANCHOR]
    beta_cache = {
        days: parent.rolling_beta(returns[MID_ALTS], btc_returns, days)
        for days in [7, 30, 90]
    }
    shock_cache: dict[float, pd.DatetimeIndex] = {}
    for quantile in [0.95, 0.975, 0.99]:
        threshold = (
            btc_returns.abs()
            .rolling(parent.SHOCK_WINDOW_BARS, min_periods=parent.SHOCK_WINDOW_BARS)
            .quantile(quantile)
            .shift(1)
        )
        shock_cache[quantile] = parent.select_events(
            btc_returns.abs() > threshold, parent.COOLDOWN_BARS
        )
    results: list[dict[str, Any]] = []
    primary_detail: dict[str, Any] | None = None
    for config in parent.CONFIGS:
        result, detail = parent.analyze_config(
            config, matrices, phase, beta_cache=beta_cache, shock_cache=shock_cache
        )
        results.append(result)
        if config.name == "primary":
            primary_detail = detail
    assert primary_detail is not None
    phase_gate = parent.development_gate(results[0])
    release_next = bool(phase_gate["pass"] and phase != "confirmation")
    if not phase_gate["pass"]:
        conclusion = "DOES_NOT_SUPPORT"
    elif phase == "confirmation":
        conclusion = "SUPPORTS_WITHIN_SCOPE"
    else:
        conclusion = "INSUFFICIENT_EVIDENCE"
    output = {
        "phase": phase,
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "study_code_sha256": code_sha256(),
        "parent_code_sha256": EXPECTED_PARENT_CODE_SHA,
        "market_universe_sha256": EXPECTED_UNIVERSE_SHA,
        "selection_rule": checkpoint()["selection_rule"],
        "environment": {
            "python": sys.version.split()[0],
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "statsmodels": sm.__version__,
            "vectorbt": vbt.__version__,
        },
        "source_identity": source_identity,
        "data_quality": quality,
        "configs": results,
        "per_asset_primary_exploratory": parent.per_asset_results(
            primary_detail, matrices, phase
        ),
        "gate": phase_gate,
        "release_next_phase": release_next,
        "conclusion": conclusion,
        "economic_warning": (
            "12/32/52 bps are only comparison floors. No historical spread/depth, funding, "
            "partial fills, mark price, margin, liquidation, delisting or manipulation model."
        ),
    }
    path = STUDY_DIR / f"{phase}.json"
    path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    latest = DATA_ROOT / f"btc-shock-mid-activity-beta-gap-{phase}-latest.json"
    latest.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "phase": phase,
                "output": str(path),
                "conclusion": conclusion,
                "release_next_phase": release_next,
                "primary": results[0]["primary"],
                "gate": phase_gate,
            },
            indent=2,
        )
    )


def self_test() -> None:
    if selected_universe() != MID_ALTS:
        raise AssertionError("selection rule self-test failed")
    parent.synthetic_self_test()
    print(json.dumps({"status": "PASS", "tests": ["fixed universe selection", "parent analysis invariants"]}, indent=2))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("verify-plan")
    commands.add_parser("self-test")
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--phase", choices=PHASES, required=True)
    prepare_parser.add_argument("--workers", type=int, default=4)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--phase", choices=PHASES, required=True)
    return result


def main() -> None:
    args = parser().parse_args()
    if args.command == "verify-plan":
        verify_plan()
    elif args.command == "self-test":
        self_test()
    elif args.command == "prepare":
        prepare(args.phase, args.workers)
    elif args.command == "run":
        run(args.phase)


if __name__ == "__main__":
    main()
