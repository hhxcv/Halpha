from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

from halpha.configuration import load_settings, settings_digest
from halpha.domain_values import content_digest
from halpha.planning.registry import OneShotParameters
from tools.qualification.prepare_b04_live_read_only_observation import prepare


ROOT = Path(__file__).resolve().parents[2]


def test_prepare_freezes_historical_parameters_and_exact_duration(tmp_path) -> None:
    parameters = OneShotParameters(direction="LONG")
    preregistration = {
        "stage": "B04_HISTORICAL_PREREGISTRATION",
        "status": "FROZEN_BEFORE_HOLDOUT_READ",
        "evidence_digest": "2" * 64,
        "strategy": {
            "strategy_id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
            "strategy_version": "1.0.0",
            "parameters": parameters.model_dump(mode="json"),
            "parameter_digest": content_digest(parameters.model_dump(mode="json")),
        },
        "capital": {
            "max_allowed_loss": "50",
            "max_notional": "500",
            "max_margin": "100",
            "effective_leverage": "5",
        },
    }
    preregistration_path = tmp_path / "preregistration.json"
    preregistration_path.write_text(json.dumps(preregistration), encoding="utf-8")
    starts_at = datetime(2026, 7, 18, tzinfo=UTC)

    spec = prepare(
        config_path=ROOT / "config/halpha.live-read-only.example.toml",
        preregistration_path=preregistration_path,
        starts_at=starts_at,
    )

    assert spec.parameters == parameters
    assert spec.schema_version == 3
    assert spec.configuration_digest == settings_digest(
        load_settings(ROOT / "config/halpha.live-read-only.example.toml")
    )
    assert spec.strategy_evidence_digest == "2" * 64
    assert spec.source_sha256_digest == content_digest(spec.source_sha256)
    assert "src/halpha/executor/forward_observation.py" in spec.source_sha256
    assert "src/halpha/planning/adapter.py" in spec.source_sha256
    assert "tools/qualification/verify_b04_live_read_only.py" in spec.source_sha256
    assert spec.minimum_end_at == starts_at + timedelta(days=7)
    assert spec.maximum_end_at == starts_at + timedelta(days=14)
    assert spec.max_notional == "500"
