"""Falsification-only robustness qualification for the fixed TRX/PAXG transfer."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd


STUDY_DIR = Path(__file__).resolve().parent
TRANSFER_PATH = STUDY_DIR / "study.py"
SEED = 20260722
BLOCK_DAYS = 30
BOOTSTRAP_SAMPLES = 20_000
WEIGHT_NEIGHBORHOOD = ((0.20, 0.30), (0.25, 0.25), (0.30, 0.20))


def _load_transfer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "halpha_trx_paxg_transfer", TRANSFER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("TRANSFER_STUDY_IMPORT_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TRANSFER = _load_transfer()
BASE = TRANSFER.BASE


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _funding_stress(market: Any) -> Any:
    def stress(values: np.ndarray) -> np.ndarray:
        return np.where(values > 0.0, values * 2.0, values)

    return BASE.MarketData(
        open_time=market.open_time.copy(),
        open=market.open.copy(),
        high=market.high.copy(),
        low=market.low.copy(),
        close=market.close.copy(),
        funding_boundary_value=stress(market.funding_boundary_value),
        funding_intraday_value=stress(market.funding_intraday_value),
        manifest_identity=market.manifest_identity,
        quality=market.quality,
    )


def _bootstrap(returns: np.ndarray) -> dict[str, float]:
    rng = np.random.default_rng(SEED)
    count = len(returns)
    blocks = int(np.ceil(count / BLOCK_DAYS))
    hurdle_total = (1.0 + TRANSFER.ANNUAL_CAPITAL_HURDLE) ** (count / 365.25) - 1.0
    totals: list[np.ndarray] = []
    drawdowns: list[np.ndarray] = []
    for offset in range(0, BOOTSTRAP_SAMPLES, 1000):
        batch = min(1000, BOOTSTRAP_SAMPLES - offset)
        starts = rng.integers(0, count, size=(batch, blocks))
        block_offsets = np.arange(BLOCK_DAYS)
        indices = (starts[:, :, None] + block_offsets[None, None, :]) % count
        samples = returns[indices.reshape(batch, -1)[:, :count]]
        equity = np.cumprod(1.0 + samples, axis=1)
        totals.append(equity[:, -1] - 1.0)
        peaks = np.maximum.accumulate(
            np.concatenate((np.ones((batch, 1)), equity), axis=1), axis=1
        )
        paths = np.concatenate((np.ones((batch, 1)), equity), axis=1)
        drawdowns.append(np.min(paths / peaks - 1.0, axis=1))
    total_array = np.concatenate(totals)
    drawdown_array = np.concatenate(drawdowns)
    return {
        "samples": BOOTSTRAP_SAMPLES,
        "block_days": BLOCK_DAYS,
        "seed": SEED,
        "probability_total_positive": float(np.mean(total_array > 0.0)),
        "probability_above_4pct_annual_hurdle": float(
            np.mean(total_array > hurdle_total)
        ),
        "total_return_p05": float(np.quantile(total_array, 0.05)),
        "total_return_p50": float(np.quantile(total_array, 0.50)),
        "total_return_p95": float(np.quantile(total_array, 0.95)),
        "max_drawdown_p05": float(np.quantile(drawdown_array, 0.05)),
    }


def _after_hurdle(metrics: dict[str, Any]) -> float:
    return (1.0 + metrics["total_return"]) / (
        (1.0 + TRANSFER.ANNUAL_CAPITAL_HURDLE) ** (metrics["days"] / 365.25)
    ) - 1.0


def qualify(args: argparse.Namespace) -> None:
    transfer_result_path = Path(args.transfer_result).resolve()
    transfer_gate_path = Path(args.transfer_gate).resolve()
    transfer_result = json.loads(transfer_result_path.read_text(encoding="utf-8"))
    transfer_gate = json.loads(transfer_gate_path.read_text(encoding="utf-8"))
    if not transfer_gate.get("research_supports_demo_candidate"):
        raise ValueError("TRANSFER_GATE_NOT_PASSED")
    trx, paxg, _ = TRANSFER._load_pair(args)
    costs = TRANSFER.SCENARIOS["stress"]
    neighborhood: dict[str, dict[str, Any]] = {}
    base_returns: np.ndarray | None = None
    base_dates: pd.DatetimeIndex | None = None
    for trx_weight, paxg_weight in WEIGHT_NEIGHBORHOOD:
        key = f"trx_{trx_weight:.2f}_paxg_{paxg_weight:.2f}"
        metrics, returns, dates = TRANSFER._simulate(
            trx,
            paxg,
            (trx_weight, paxg_weight),
            fee_rate=costs["fee"],
            slippage_rate=costs["slippage"],
            include_funding=True,
        )
        neighborhood[key] = {
            "metrics": metrics,
            "return_after_4pct_annual_hurdle": _after_hurdle(metrics),
        }
        if (trx_weight, paxg_weight) == (0.25, 0.25):
            base_returns, base_dates = returns, dates
    if base_returns is None or base_dates is None:
        raise AssertionError("BASE_ROBUSTNESS_RETURNS_MISSING")
    adverse_metrics, _, _ = TRANSFER._simulate(
        _funding_stress(trx),
        _funding_stress(paxg),
        (0.25, 0.25),
        fee_rate=costs["fee"],
        slippage_rate=costs["slippage"],
        include_funding=True,
    )
    series = pd.Series(base_returns, index=base_dates)
    month_growth = (
        (1.0 + series).groupby([series.index.year, series.index.month]).prod()
    )
    best_month = month_growth.idxmax()
    without_best = series.copy()
    without_best.loc[
        (without_best.index.year == best_month[0])
        & (without_best.index.month == best_month[1])
    ] = 0.0
    without_best_total = float((1.0 + without_best).prod() - 1.0)
    without_best_hurdle = (1.0 + without_best_total) / (
        (1.0 + TRANSFER.ANNUAL_CAPITAL_HURDLE) ** (len(without_best) / 365.25)
    ) - 1.0
    bootstrap = _bootstrap(base_returns)
    checks = {
        "all_weight_neighbors_above_4pct_hurdle": all(
            item["return_after_4pct_annual_hurdle"] > 0
            for item in neighborhood.values()
        ),
        "all_weight_neighbors_drawdown_above_minus_12pct": all(
            item["metrics"]["max_drawdown"] > -0.12 for item in neighborhood.values()
        ),
        "doubled_positive_funding_above_4pct_hurdle": _after_hurdle(adverse_metrics)
        > 0,
        "doubled_positive_funding_drawdown_above_minus_12pct": adverse_metrics[
            "max_drawdown"
        ]
        > -0.12,
        "without_best_month_above_4pct_hurdle": without_best_hurdle > 0,
        "bootstrap_probability_positive_at_least_0p80": bootstrap[
            "probability_total_positive"
        ]
        >= 0.80,
        "bootstrap_probability_hurdle_at_least_0p65": bootstrap[
            "probability_above_4pct_annual_hurdle"
        ]
        >= 0.65,
        "bootstrap_drawdown_p05_above_minus_20pct": bootstrap["max_drawdown_p05"]
        > -0.20,
    }
    failed = [name for name, passed in checks.items() if not passed]
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "phase": "venue_transfer_robustness",
        "method_identity": {
            "robustness_sha256": _sha256(Path(__file__).resolve()),
            "transfer_study_sha256": _sha256(TRANSFER_PATH),
            "transfer_result_sha256": _sha256(transfer_result_path),
            "transfer_gate_sha256": _sha256(transfer_gate_path),
            "candidate_id": transfer_result["candidate"]["candidate_id"],
        },
        "weight_neighborhood_stress_costs": neighborhood,
        "doubled_positive_funding_stress_costs": {
            "metrics": adverse_metrics,
            "return_after_4pct_annual_hurdle": _after_hurdle(adverse_metrics),
        },
        "best_month_removal_stress_costs": {
            "removed_month": f"{best_month[0]:04d}-{best_month[1]:02d}",
            "removed_month_return": float(month_growth.loc[best_month] - 1.0),
            "total_return": without_best_total,
            "return_after_4pct_annual_hurdle": without_best_hurdle,
        },
        "circular_block_bootstrap_stress_returns": bootstrap,
        "checks": checks,
        "failed_checks": failed,
        "robustness_supports_demo_candidate": not failed,
        "conclusion": "SUPPORTS_ROBUSTNESS" if not failed else "DOES_NOT_SUPPORT",
        "product_effects": "NONE",
    }
    Path(args.output).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"checks": checks, "failed_checks": failed}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transfer-result", required=True)
    parser.add_argument("--transfer-gate", required=True)
    parser.add_argument("--trx-cache-root", required=True)
    parser.add_argument("--trx-manifest", required=True)
    parser.add_argument("--paxg-cache-root", required=True)
    parser.add_argument("--paxg-manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    qualify(args)


if __name__ == "__main__":
    main()
