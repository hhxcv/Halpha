"""Taker-flow alignment filter for the current one-shot BTCUSDT proxy."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


FOUNDATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "btcusdt-one-shot-funding-sign-filter"
    / "study.py"
)
EXPECTED_FOUNDATION_SHA256 = (
    "3dc692689fb279df88105868391e33de49726e83df36914234c774ba20b3b41c"
)
MODULE_NAME = "halpha_funding_filter_foundation_for_taker_flow"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, FOUNDATION_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("FOUNDATION_STUDY_IMPORT_FAILED")
foundation = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = foundation
SPEC.loader.exec_module(foundation)
if foundation.parent._sha256(FOUNDATION_PATH) != EXPECTED_FOUNDATION_SHA256:
    raise RuntimeError("FOUNDATION_STUDY_SHA256_MISMATCH")


parent = foundation.parent
np = parent.np
pd = parent.pd
vbt = parent.vbt
nb = parent.nb

PERIODS = parent.PERIODS
SCENARIOS = parent.SCENARIOS
DIRECTIONS = (1, -1)
LOOKBACK = 20
CONFIRMATION = 2
EXTENSION = 0.5
FILTER_NAME = "CONFIRMATION_TAKER_FLOW_ALIGNED"
BASELINE_NAME = "UNFILTERED"


def _load_signed_taker_flow(
    *,
    cache_root: Path,
    manifest_path: Path,
    expected_open_time: Any,
) -> tuple[Any, dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    start_month = parent._month_key(int(expected_open_time[0]))
    end_month = parent._month_key(int(expected_open_time[-1]))
    archives = [
        item
        for item in manifest["archives"]
        if start_month <= item["month"] <= end_month
    ]
    frames: list[Any] = []
    for item in archives:
        archive = cache_root / item["cache_relative_path"]
        if parent._sha256(archive) != item["sha256"]:
            raise ValueError(f"ARCHIVE_SHA256_MISMATCH:{archive.name}")
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            if len(names) != 1:
                raise ValueError(f"ARCHIVE_MEMBER_COUNT_INVALID:{archive.name}")
            with bundle.open(names[0]) as source:
                first_line = source.readline().strip().lower()
                source.seek(0)
                skiprows = 1 if first_line.startswith(b"open_time") else 0
                frames.append(
                    pd.read_csv(
                        source,
                        header=None,
                        skiprows=skiprows,
                        usecols=(0, 5, 9),
                        names=("open_time", "volume", "taker_buy_volume"),
                        dtype={
                            "open_time": "int64",
                            "volume": "float64",
                            "taker_buy_volume": "float64",
                        },
                    )
                )
    frame = pd.concat(frames, ignore_index=True)
    frame = frame.loc[
        (frame["open_time"] >= int(expected_open_time[0]))
        & (frame["open_time"] <= int(expected_open_time[-1]))
    ].sort_values("open_time", kind="stable")
    frame = frame.drop_duplicates("open_time", keep=False).reset_index(drop=True)
    actual_open_time = frame["open_time"].to_numpy(dtype=np.int64, copy=True)
    if not np.array_equal(actual_open_time, expected_open_time):
        raise ValueError("TAKER_FLOW_TIMELINE_MISMATCH")
    volume = frame["volume"].to_numpy(dtype=np.float64, copy=True)
    taker_buy = frame["taker_buy_volume"].to_numpy(dtype=np.float64, copy=True)
    valid = (
        np.isfinite(volume)
        & np.isfinite(taker_buy)
        & (volume > 0.0)
        & (taker_buy >= 0.0)
        & (taker_buy <= volume)
    )
    signed_flow = np.full(len(volume), np.nan, dtype=np.float64)
    signed_flow[valid] = 2.0 * taker_buy[valid] - volume[valid]
    return signed_flow, {
        "taker_flow_archives": len(archives),
        "taker_flow_valid_bars": int(np.sum(valid)),
        "taker_flow_invalid_bars": int(np.sum(~valid)),
        "taker_flow_zero_bars": int(np.sum(valid & (signed_flow == 0.0))),
    }


def _confirmation_flow(signed_flow: Any, trigger_indices: Any) -> Any:
    previous = trigger_indices - 1
    if np.any(previous < 0):
        raise ValueError("CONFIRMATION_FLOW_WINDOW_INVALID")
    return signed_flow[previous] + signed_flow[trigger_indices]


def _config_id(direction: int, filtered: bool) -> str:
    side = "LONG" if direction == 1 else "SHORT"
    return f"{side}:{FILTER_NAME if filtered else BASELINE_NAME}"


def _run_config(
    data: Any,
    indicators: tuple[Any, Any, Any],
    signed_flow: Any,
    *,
    direction: int,
    filtered: bool,
    start_ms: int,
    end_ms: int,
) -> dict[str, Any]:
    upper, lower, atr = indicators
    raw_triggers = parent._trigger_indices(
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
    raw_flow = _confirmation_flow(signed_flow, raw_triggers)
    known = np.isfinite(raw_flow)
    if filtered:
        triggers = raw_triggers[known & (direction * raw_flow > 0.0)]
    else:
        triggers = raw_triggers
    boundary = upper + EXTENSION * atr if direction == 1 else lower - EXTENSION * atr
    result: dict[str, Any] = {
        "config_id": _config_id(direction, filtered),
        "direction": "LONG" if direction == 1 else "SHORT",
        "filter": FILTER_NAME if filtered else BASELINE_NAME,
        "channel_lookback_15m": LOOKBACK,
        "confirmation_bars_1m": CONFIRMATION,
        "max_entry_extension_atr": EXTENSION,
        "raw_trigger_count": int(len(raw_triggers)),
        "eligible_trigger_count": int(len(triggers)),
        "eligible_trigger_fraction": (
            float(len(triggers) / len(raw_triggers)) if len(raw_triggers) else None
        ),
        "confirmation_flow_signs": {
            "positive": int(np.sum(raw_flow[known] > 0.0)),
            "negative": int(np.sum(raw_flow[known] < 0.0)),
            "zero": int(np.sum(raw_flow[known] == 0.0)),
            "unknown": int(np.sum(~known)),
        },
    }
    for name, (fee, adverse) in SCENARIOS.items():
        returns, entry_indices, _ = parent._simulate(
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
        )
        result[name] = foundation._metrics(returns, data.open_time[entry_indices])
    return result


def _flatten(result: dict[str, Any], *, candidate: bool) -> dict[str, Any]:
    row: dict[str, Any] = {
        "config_id": result["config_id"],
        "selected_candidate": candidate,
        "direction": result["direction"],
        "filter": result["filter"],
        "raw_trigger_count": result["raw_trigger_count"],
        "eligible_trigger_count": result["eligible_trigger_count"],
        "eligible_trigger_fraction": result["eligible_trigger_fraction"],
    }
    for sign, count in result["confirmation_flow_signs"].items():
        row[f"confirmation_flow_{sign}"] = count
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
        ):
            row[f"{scenario}_{key}"] = metrics[key]
        for year, value in metrics["annual_means"].items():
            row[f"{scenario}_mean_{year}"] = value
    return row


def _candidate_from_row(row: Any) -> dict[str, Any]:
    return {
        "config_id": str(row["config_id"]),
        "direction": str(row["direction"]),
        "filter": str(row["filter"]),
    }


def _configs_for_phase(
    phase: str, authorization: dict[str, Any] | None
) -> list[tuple[int, bool]]:
    if phase == "development":
        return [
            (direction, filtered)
            for direction in DIRECTIONS
            for filtered in (False, True)
        ]
    if authorization is None:
        raise ValueError("AUTHORIZATION_REQUIRED")
    key = "selected_candidates" if phase == "evaluation" else "confirmation_candidate"
    raw = authorization.get(key)
    candidates = raw if isinstance(raw, list) else ([raw] if isinstance(raw, dict) else [])
    if not candidates:
        raise ValueError("AUTHORIZED_CANDIDATE_MISSING")
    configs: list[tuple[int, bool]] = []
    for item in candidates:
        direction = 1 if item["direction"] == "LONG" else -1
        configs.extend(((direction, True), (direction, False)))
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
    signed_flow, flow_quality = _load_signed_taker_flow(
        cache_root=Path(args.cache_root),
        manifest_path=Path(args.manifest),
        expected_open_time=data.open_time,
    )
    indicators = parent._target_indicators(data, LOOKBACK)
    details: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for direction, filtered in configs:
        result = _run_config(
            data,
            indicators,
            signed_flow,
            direction=direction,
            filtered=filtered,
            start_ms=start_ms,
            end_ms=end_ms,
        )
        details.append(result)
        rows.append(_flatten(result, candidate=filtered))

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
        "foundation_study_sha256": EXPECTED_FOUNDATION_SHA256,
        "data_identity": data.manifest_identity,
        "data_quality": {**data.data_quality, **flow_quality},
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
    print(json.dumps({"phase": args.phase, "rows": len(rows)}))


def _same_direction_baseline(frame: Any, row: Any) -> Any:
    baseline = frame.loc[
        (frame["direction"] == row["direction"])
        & (frame["filter"] == BASELINE_NAME)
    ]
    if baseline.empty:
        raise ValueError("SAME_DIRECTION_BASELINE_MISSING")
    return baseline.iloc[0]


def select_development(args: argparse.Namespace) -> None:
    source = Path(args.input)
    frame = pd.read_csv(source)
    candidates = frame.loc[frame["selected_candidate"] == True].copy()  # noqa: E712
    passed: list[Any] = []
    for _, row in candidates.iterrows():
        baseline = _same_direction_baseline(frame, row)
        annual = [float(row[f"base_mean_{year}"]) for year in (2021, 2022, 2023)]
        delta = float(row["base_mean"]) - float(baseline["base_mean"])
        if (
            int(row["base_trades"]) >= 100
            and float(row["base_mean"]) > 0.0
            and float(row["stress_mean"]) > 0.0
            and sum(value > 0.0 for value in annual) >= 2
            and min(annual) >= -0.001
            and delta >= 0.0005
            and float(row["base_p01"]) >= -0.02
            and float(row["base_worst"]) >= -0.05
        ):
            row = row.copy()
            row["worst_annual_base_mean"] = min(annual)
            row["base_improvement_over_unfiltered"] = delta
            passed.append(row)
    passed.sort(
        key=lambda row: (
            -float(row["worst_annual_base_mean"]),
            -float(row["stress_mean"]),
            -float(row["base_mean"]),
            -float(row["base_improvement_over_unfiltered"]),
            str(row["config_id"]),
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
        "stop_reason": (
            None if selected else "NO_TAKER_FLOW_DIRECTION_PASSED_DEVELOPMENT_GATE"
        ),
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
        baseline = _same_direction_baseline(frame, row)
        delta = float(row["base_mean"]) - float(baseline["base_mean"])
        if (
            int(row["base_trades"]) >= 60
            and float(row["base_mean"]) > 0.0
            and float(row["stress_mean"]) > 0.0
            and float(row["base_mean_2024"]) > 0.0
            and float(row["base_mean_2025"]) > 0.0
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
        "stop_reason": (
            None if candidate else "FIXED_TAKER_FLOW_FILTER_FAILED_EVALUATION_GATE"
        ),
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
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
