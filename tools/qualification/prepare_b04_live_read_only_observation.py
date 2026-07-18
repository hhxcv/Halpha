"""Freeze one read-only observation spec after external identities are ready."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from halpha.configuration import load_settings, settings_digest
from halpha.domain_values import content_digest
from halpha.executor.forward_observation import ForwardObservationSpec
from halpha.planning.registry import OneShotParameters
DEFAULT_CONFIG = ROOT / "config/halpha.live-read-only.toml"
DEFAULT_PREREGISTRATION = (
    ROOT / "build/evidence/reports/b04-historical-preregistration.json"
)
DEFAULT_OUTPUT = ROOT / "build/evidence/reports/b04-live-read-only-spec.json"


class ForwardObservationPreparationError(RuntimeError):
    """Sanitized refusal to begin an invalid observation window."""


def prepare(
    *,
    config_path: Path,
    preregistration_path: Path,
    starts_at: datetime,
) -> ForwardObservationSpec:
    settings = load_settings(config_path)
    if settings.release.profile != "BINANCE_LIVE_READ_ONLY":
        raise ForwardObservationPreparationError("READ_ONLY_PROFILE_REQUIRED")
    if (
        settings.executor.binance_api_key_reference is not None
        or settings.executor.binance_api_secret_reference is not None
    ):
        raise ForwardObservationPreparationError(
            "READ_ONLY_BINANCE_CREDENTIAL_MUST_BE_ABSENT"
        )
    try:
        preregistration = json.loads(preregistration_path.read_text(encoding="utf-8"))
        strategy = preregistration["strategy"]
        capital = preregistration["capital"]
        if (
            preregistration["stage"] != "B04_HISTORICAL_PREREGISTRATION"
            or preregistration["status"] != "FROZEN_BEFORE_HOLDOUT_READ"
            or strategy["strategy_id"] != "ONE_SHOT_DONCHIAN_ATR_BREAKOUT"
            or strategy["strategy_version"] != "1.0.0"
        ):
            raise ForwardObservationPreparationError(
                "HISTORICAL_PREREGISTRATION_IDENTITY_INVALID"
            )
        parameters = OneShotParameters.model_validate(strategy["parameters"])
        parameter_digest = content_digest(parameters.model_dump(mode="json"))
        if parameter_digest != strategy["parameter_digest"]:
            raise ForwardObservationPreparationError(
                "HISTORICAL_PREREGISTRATION_PARAMETER_DRIFT"
            )
        evidence_digest = str(preregistration["evidence_digest"])
        if len(evidence_digest) != 64:
            raise ForwardObservationPreparationError(
                "HISTORICAL_PREREGISTRATION_DIGEST_INVALID"
            )
    except ForwardObservationPreparationError:
        raise
    except Exception as exc:
        raise ForwardObservationPreparationError(
            f"HISTORICAL_PREREGISTRATION_INVALID type={type(exc).__name__}"
        ) from None

    starts_at = starts_at.astimezone(UTC)
    observation_date = starts_at.strftime("%Y%m%d")
    return ForwardObservationSpec(
        observation_id=f"b04-live-read-only-{observation_date}",
        activation_id=f"b04-live-read-only-btcusdt-{observation_date}",
        strategy_evidence_digest=evidence_digest,
        configuration_digest=settings_digest(settings),
        parameters=parameters,
        parameter_digest=parameter_digest,
        starts_at=starts_at,
        minimum_end_at=starts_at + timedelta(days=7),
        maximum_end_at=starts_at + timedelta(days=14),
        max_allowed_loss=str(capital["max_allowed_loss"]),
        max_notional=str(capital["max_notional"]),
        max_margin=str(capital["max_margin"]),
        effective_leverage=str(capital["effective_leverage"]),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--preregistration", type=Path, default=DEFAULT_PREREGISTRATION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--initialize", action="store_true")
    args = parser.parse_args(argv)
    if not args.initialize:
        raise ForwardObservationPreparationError(
            "EXPLICIT_FORWARD_OBSERVATION_INITIALIZATION_REQUIRED"
        )
    output = args.output.resolve()
    evidence_root = (ROOT / "build/evidence/reports").resolve()
    if not output.is_relative_to(evidence_root):
        raise ForwardObservationPreparationError("OBSERVATION_SPEC_OUTSIDE_EVIDENCE_ROOT")
    if output.exists():
        raise ForwardObservationPreparationError("OBSERVATION_SPEC_ALREADY_EXISTS")
    spec = prepare(
        config_path=args.config.resolve(),
        preregistration_path=args.preregistration.resolve(),
        starts_at=datetime.now(UTC),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(
        json.dumps(spec.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(output)
    print(
        json.dumps(
            {
                "status": "FORWARD_OBSERVATION_SPEC_FROZEN",
                "observation_id": spec.observation_id,
                "starts_at": spec.starts_at.isoformat(),
                "minimum_end_at": spec.minimum_end_at.isoformat(),
                "maximum_end_at": spec.maximum_end_at.isoformat(),
                "contains_secret": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
