"""Bounded maximum-hold study for the current one-shot BTCUSDT strategy proxy.

The script reuses the locked parent study's public-data parser, indicators,
trigger definition, metrics, and dependency environment. It does not import
Halpha product code, read a product database, or call a trading endpoint.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PARENT_PATH = (
    Path(__file__).resolve().parent.parent
    / "btcusdt-one-shot-entry-selectivity"
    / "study.py"
)
EXPECTED_PARENT_SHA256 = (
    "1450814102dd0fca73903c4221aae9797f0ae6eef11691fb23dea8eeb2eac0ec"
)
MODULE_NAME = "halpha_entry_selectivity_parent"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, PARENT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("PARENT_STUDY_IMPORT_FAILED")
parent = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = parent
SPEC.loader.exec_module(parent)
if parent._sha256(PARENT_PATH) != EXPECTED_PARENT_SHA256:
    raise RuntimeError("PARENT_STUDY_SHA256_MISMATCH")


np = parent.np
pd = parent.pd
nb = parent.nb
vbt = parent.vbt

CANDIDATE_HOLD_BARS = (8, 16, 32)
EXPOSED_BENCHMARK_HOLD_BARS = (4, 96)
ALL_DEVELOPMENT_HOLD_BARS = (*EXPOSED_BENCHMARK_HOLD_BARS, *CANDIDATE_HOLD_BARS)
DIRECTIONS = (1, -1)
PERIODS = parent.PERIODS
SCENARIOS = parent.SCENARIOS
LOOKBACK = 20
CONFIRMATION = 2
EXTENSION = 0.5


@nb.njit(cache=True)
def _simulate_hold(
    trigger_indices: Any,
    open_price: Any,
    high: Any,
    low: Any,
    funding_rate: Any,
    funding_mark: Any,
    atr: Any,
    boundary: Any,
    direction: int,
    fee: float,
    adverse_execution: float,
    max_hold_minutes: int,
) -> tuple[Any, Any, Any]:
    returns = np.empty(len(trigger_indices), dtype=np.float64)
    entries = np.empty(len(trigger_indices), dtype=np.int64)
    exits = np.empty(len(trigger_indices), dtype=np.int64)
    count = 0
    next_trigger = 0
    for trigger in trigger_indices:
        if trigger < next_trigger:
            continue
        entry_index = trigger + 1
        time_exit_index = entry_index + max_hold_minutes
        if time_exit_index >= len(open_price):
            break
        raw_entry = open_price[entry_index]
        conservative_entry = raw_entry * (1.0 + direction * adverse_execution)
        if direction == 1 and conservative_entry > boundary[trigger]:
            continue
        if direction == -1 and conservative_entry < boundary[trigger]:
            continue
        entry_fill = conservative_entry
        risk = 1.5 * atr[trigger]
        stop = entry_fill - direction * risk
        tp1 = entry_fill + direction * risk * 1.5
        tp2 = entry_fill + direction * risk * 3.0
        remaining = 1.0
        pnl = -fee * entry_fill / raw_entry
        exited_at = time_exit_index

        for minute in range(entry_index, time_exit_index):
            if minute > entry_index and funding_rate[minute] != 0.0:
                mark = funding_mark[minute]
                if mark <= 0.0:
                    mark = open_price[minute]
                pnl += -direction * funding_rate[minute] * remaining * mark / raw_entry

            if direction == 1:
                stop_hit = low[minute] <= stop
                tp1_hit = remaining > 0.5 and high[minute] >= tp1
                tp2_hit = high[minute] >= tp2
            else:
                stop_hit = high[minute] >= stop
                tp1_hit = remaining > 0.5 and low[minute] <= tp1
                tp2_hit = low[minute] <= tp2

            if stop_hit:
                raw_fill = stop
                if direction == 1 and open_price[minute] < stop:
                    raw_fill = open_price[minute]
                elif direction == -1 and open_price[minute] > stop:
                    raw_fill = open_price[minute]
                exit_fill = raw_fill * (1.0 - direction * adverse_execution)
                pnl += direction * (exit_fill - entry_fill) * remaining / raw_entry
                pnl -= fee * exit_fill * remaining / raw_entry
                remaining = 0.0
                exited_at = minute
                break

            if tp1_hit:
                fraction = 0.5
                exit_fill = tp1 * (1.0 - direction * adverse_execution)
                pnl += direction * (exit_fill - entry_fill) * fraction / raw_entry
                pnl -= fee * exit_fill * fraction / raw_entry
                remaining -= fraction
            if tp2_hit and remaining > 0.0:
                exit_fill = tp2 * (1.0 - direction * adverse_execution)
                pnl += direction * (exit_fill - entry_fill) * remaining / raw_entry
                pnl -= fee * exit_fill * remaining / raw_entry
                remaining = 0.0
                exited_at = minute
                break

        if remaining > 0.0:
            raw_fill = open_price[time_exit_index]
            exit_fill = raw_fill * (1.0 - direction * adverse_execution)
            pnl += direction * (exit_fill - entry_fill) * remaining / raw_entry
            pnl -= fee * exit_fill * remaining / raw_entry
        returns[count] = pnl
        entries[count] = entry_index
        exits[count] = exited_at
        count += 1
        next_trigger = exited_at + 1
    return returns[:count], entries[:count], exits[:count]


def _metrics(returns: Any, entry_times: Any, entries: Any, exits: Any) -> dict[str, Any]:
    metrics = parent._metrics(returns, entry_times)
    if len(returns) == 0:
        metrics.update({"p01": None, "worst": None, "mean_holding_hours": None})
    else:
        metrics.update(
            {
                "p01": float(np.quantile(returns, 0.01)),
                "worst": float(np.min(returns)),
                "mean_holding_hours": float(np.mean(exits - entries) / 60.0),
            }
        )
    return metrics


def _config_id(direction: int, hold_bars: int) -> str:
    return f"{'LONG' if direction == 1 else 'SHORT'}:HOLD:{hold_bars}"


def _run_config(
    data: Any,
    indicators: tuple[Any, Any, Any],
    *,
    direction: int,
    hold_bars: int,
    start_ms: int,
    end_ms: int,
) -> dict[str, Any]:
    upper, lower, atr = indicators
    triggers = parent._trigger_indices(
        data,
        upper=upper,
        lower=lower,
        atr=atr,
        confirmation=CONFIRMATION,
        extension=EXTENSION,
        direction=direction,
        start_ms=start_ms,
        end_ms=end_ms,
    )
    max_hold_minutes = hold_bars * 15
    enough_phase_time = (
        data.open_time[triggers] + (max_hold_minutes + 1) * 60_000 < end_ms
    )
    triggers = triggers[enough_phase_time]
    boundary = upper + EXTENSION * atr if direction == 1 else lower - EXTENSION * atr
    result: dict[str, Any] = {
        "config_id": _config_id(direction, hold_bars),
        "direction": "LONG" if direction == 1 else "SHORT",
        "max_hold_bars_15m": hold_bars,
        "max_hold_hours": hold_bars / 4.0,
        "raw_trigger_count": int(len(triggers)),
    }
    for name, (fee, adverse) in SCENARIOS.items():
        returns, entries, exits = _simulate_hold(
            triggers,
            data.open,
            data.high,
            data.low,
            data.funding_rate,
            data.funding_mark,
            atr,
            boundary,
            direction,
            fee,
            adverse,
            max_hold_minutes,
        )
        result[name] = _metrics(
            returns,
            data.open_time[entries],
            entries,
            exits,
        )
    return result


def _flatten(result: dict[str, Any], *, selected_candidate: bool) -> dict[str, Any]:
    row = {
        "config_id": result["config_id"],
        "selected_candidate": selected_candidate,
        "direction": result["direction"],
        "max_hold_bars_15m": result["max_hold_bars_15m"],
        "max_hold_hours": result["max_hold_hours"],
        "raw_trigger_count": result["raw_trigger_count"],
    }
    for scenario in SCENARIOS:
        metrics = result[scenario]
        for key in (
            "trades",
            "mean",
            "median",
            "win_rate",
            "total_compound",
            "max_drawdown",
            "standard_error",
            "p01",
            "worst",
            "mean_holding_hours",
        ):
            row[f"{scenario}_{key}"] = metrics[key]
        for year, value in metrics["annual_means"].items():
            row[f"{scenario}_mean_{year}"] = value
    return row


def _candidate_from_row(row: Any) -> dict[str, Any]:
    return {
        "config_id": str(row["config_id"]),
        "direction": str(row["direction"]),
        "max_hold_bars_15m": int(row["max_hold_bars_15m"]),
    }


def _configs_for_phase(
    phase: str, authorization: dict[str, Any] | None
) -> list[tuple[int, int, bool]]:
    if phase == "development":
        return [
            (direction, hold_bars, hold_bars in CANDIDATE_HOLD_BARS)
            for hold_bars in ALL_DEVELOPMENT_HOLD_BARS
            for direction in DIRECTIONS
        ]
    if authorization is None:
        raise ValueError("AUTHORIZATION_REQUIRED")
    key = "selected_candidates" if phase == "evaluation" else "confirmation_candidate"
    raw = authorization.get(key)
    candidates = raw if isinstance(raw, list) else ([raw] if isinstance(raw, dict) else [])
    if not candidates:
        raise ValueError("AUTHORIZED_CANDIDATE_MISSING")
    configs: list[tuple[int, int, bool]] = []
    for item in candidates:
        direction = 1 if item["direction"] == "LONG" else -1
        configs.append((direction, int(item["max_hold_bars_15m"]), True))
        configs.append((direction, 4, False))
    return list(dict.fromkeys(configs))


def analyze(args: argparse.Namespace) -> None:
    start_text, end_text = PERIODS[args.phase]
    start_ms, end_ms = parent._utc_ms(start_text), parent._utc_ms(end_text)
    authorization = (
        json.loads(Path(args.authorization).read_text(encoding="utf-8"))
        if args.authorization
        else None
    )
    configs = _configs_for_phase(args.phase, authorization)
    data = parent._load_market_data(
        cache_root=Path(args.cache_root),
        manifest_path=Path(args.manifest),
        start_ms=start_ms,
        end_ms=end_ms,
    )
    indicators = parent._target_indicators(data, LOOKBACK)
    details: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for direction, hold_bars, selected in configs:
        result = _run_config(
            data,
            indicators,
            direction=direction,
            hold_bars=hold_bars,
            start_ms=start_ms,
            end_ms=end_ms,
        )
        details.append(result)
        rows.append(_flatten(result, selected_candidate=selected))

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{args.phase}.csv"
    json_path = output_dir / f"{args.phase}.json"
    pd.DataFrame(rows).sort_values("config_id").to_csv(csv_path, index=False)
    payload = {
        "schema_version": 1,
        "phase": args.phase,
        "period": [start_text, end_text],
        "generated_at": datetime.now(UTC).isoformat(),
        "framework": {
            "vectorbt": vbt.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "numba": nb.__version__,
        },
        "parent_study_sha256": EXPECTED_PARENT_SHA256,
        "data_identity": data.manifest_identity,
        "data_quality": data.data_quality,
        "authorization_sha256": (
            parent._sha256(Path(args.authorization)) if args.authorization else None
        ),
        "configuration_count": len(rows),
        "csv_sha256": parent._sha256(csv_path),
        "results": details,
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "phase": args.phase,
                "rows": len(rows),
                "csv": str(csv_path),
                "json": str(json_path),
            }
        )
    )


def select_development(args: argparse.Namespace) -> None:
    source = Path(args.input)
    frame = pd.read_csv(source)
    candidates = frame.loc[frame["selected_candidate"] == True].copy()  # noqa: E712
    passed: list[Any] = []
    for _, row in candidates.iterrows():
        annual = [float(row[f"base_mean_{year}"]) for year in (2021, 2022, 2023)]
        if (
            int(row["base_trades"]) >= 100
            and float(row["base_mean"]) > 0
            and float(row["stress_mean"]) > 0
            and sum(value > 0 for value in annual) >= 2
            and min(annual) >= -0.001
            and float(row["base_p01"]) >= -0.02
            and float(row["base_worst"]) >= -0.05
        ):
            row = row.copy()
            row["worst_annual_base_mean"] = min(annual)
            passed.append(row)
    passed.sort(
        key=lambda row: (
            -float(row["worst_annual_base_mean"]),
            -float(row["stress_mean"]),
            -float(row["base_mean"]),
            int(row["max_hold_bars_15m"]),
        )
    )
    selected = [_candidate_from_row(passed[0])] if passed else []
    payload = {
        "schema_version": 1,
        "phase": "development_selection",
        "generated_at": datetime.now(UTC).isoformat(),
        "input_sha256": parent._sha256(source),
        "gate_pass_count": len(passed),
        "selected_candidates": selected,
        "evaluation_authorized": bool(selected),
        "stop_reason": None if selected else "NO_HOLD_HORIZON_PASSED_DEVELOPMENT_GATE",
    }
    Path(args.output).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False))


def qualify_evaluation(args: argparse.Namespace) -> None:
    source = Path(args.input)
    frame = pd.read_csv(source)
    candidates = frame.loc[frame["selected_candidate"] == True].copy()  # noqa: E712
    passers: list[Any] = []
    for _, row in candidates.iterrows():
        baseline = frame.loc[
            (frame["direction"] == row["direction"])
            & (frame["max_hold_bars_15m"] == 4)
        ]
        if baseline.empty:
            raise ValueError("SAME_DIRECTION_4_BAR_BASELINE_MISSING")
        delta = float(row["base_mean"]) - float(baseline.iloc[0]["base_mean"])
        if (
            int(row["base_trades"]) >= 60
            and float(row["base_mean"]) > 0
            and float(row["stress_mean"]) > 0
            and float(row["base_mean_2024"]) > 0
            and float(row["base_mean_2025"]) > 0
            and delta >= 0.0005
            and float(row["base_p01"]) >= -0.02
            and float(row["base_worst"]) >= -0.05
        ):
            passers.append(row)
    candidate = _candidate_from_row(passers[0]) if passers else None
    payload = {
        "schema_version": 1,
        "phase": "evaluation_gate",
        "generated_at": datetime.now(UTC).isoformat(),
        "input_sha256": parent._sha256(source),
        "pass_count": len(passers),
        "confirmation_candidate": candidate,
        "confirmation_authorized": candidate is not None,
        "stop_reason": None if candidate else "FIXED_HOLD_HORIZON_FAILED_EVALUATION_GATE",
    }
    Path(args.output).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False))


def qualify_confirmation(args: argparse.Namespace) -> None:
    evaluation = pd.read_csv(args.evaluation)
    confirmation = pd.read_csv(args.confirmation)
    evaluation_row = evaluation.loc[evaluation["selected_candidate"] == True].iloc[0]  # noqa: E712
    confirmation_row = confirmation.loc[confirmation["selected_candidate"] == True].iloc[0]  # noqa: E712
    if evaluation_row["config_id"] != confirmation_row["config_id"]:
        raise ValueError("FIXED_CANDIDATE_IDENTITY_MISMATCH")
    total_trades = int(evaluation_row["base_trades"]) + int(
        confirmation_row["base_trades"]
    )
    combined_mean = (
        float(evaluation_row["base_mean"]) * int(evaluation_row["base_trades"])
        + float(confirmation_row["base_mean"])
        * int(confirmation_row["base_trades"])
    ) / total_trades
    passed = (
        int(confirmation_row["base_trades"]) >= 15
        and float(confirmation_row["base_mean"]) > 0
        and float(confirmation_row["stress_mean"]) > 0
        and float(confirmation_row["base_p01"]) >= -0.02
        and float(confirmation_row["base_worst"]) >= -0.05
        and combined_mean > 0
    )
    payload = {
        "schema_version": 1,
        "phase": "confirmation_gate",
        "generated_at": datetime.now(UTC).isoformat(),
        "evaluation_sha256": parent._sha256(Path(args.evaluation)),
        "confirmation_sha256": parent._sha256(Path(args.confirmation)),
        "candidate": _candidate_from_row(confirmation_row),
        "combined_base_mean": combined_mean,
        "conclusion": "SUPPORTS_WITHIN_SCOPE" if passed else "DOES_NOT_SUPPORT",
        "product_effects": "NONE",
    }
    Path(args.output).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("--phase", choices=tuple(PERIODS), required=True)
    analyze_parser.add_argument("--cache-root", required=True)
    analyze_parser.add_argument("--manifest", required=True)
    analyze_parser.add_argument("--output-dir", required=True)
    analyze_parser.add_argument("--authorization")
    analyze_parser.set_defaults(func=analyze)

    select_parser = subparsers.add_parser("select-development")
    select_parser.add_argument("--input", required=True)
    select_parser.add_argument("--output", required=True)
    select_parser.set_defaults(func=select_development)

    evaluation_parser = subparsers.add_parser("qualify-evaluation")
    evaluation_parser.add_argument("--input", required=True)
    evaluation_parser.add_argument("--output", required=True)
    evaluation_parser.set_defaults(func=qualify_evaluation)

    confirmation_parser = subparsers.add_parser("qualify-confirmation")
    confirmation_parser.add_argument("--evaluation", required=True)
    confirmation_parser.add_argument("--confirmation", required=True)
    confirmation_parser.add_argument("--output", required=True)
    confirmation_parser.set_defaults(func=qualify_confirmation)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
