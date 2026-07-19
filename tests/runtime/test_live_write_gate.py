from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest

from halpha.configuration import load_settings
from halpha.live_write_gate import (
    LiveWriteGateBinding,
    LiveWriteGateError,
    assert_live_write_gate_directory_security,
    assert_live_write_gate_security,
    evaluate_live_write_gate,
    require_live_write_gate_binding_provisionable,
    require_live_write_gate_open,
    require_live_write_gate_precheck,
)
from halpha.live_write_gate_cli import (
    _apply_security,
    provision_live_write_gate_binding,
)


ROOT = Path(__file__).resolve().parents[2]
LIVE_CONFIG = ROOT / "config" / "halpha.live-write.toml"
MANIFEST_DIGEST = "a" * 64
NOW = datetime(2026, 7, 18, 12, tzinfo=UTC)


def _settings(tmp_path: Path):
    config = tmp_path / "live.toml"
    content = LIVE_CONFIG.read_text(encoding="utf-8").replace(
        "D:/projects/Codex/Halpha.runtime/live-write-gate.json",
        (tmp_path / "live-write-gate.json").as_posix(),
    )
    config.write_text(content, encoding="utf-8")
    return load_settings(config)


def _binding(settings, *, gate: str) -> LiveWriteGateBinding:
    return LiveWriteGateBinding(
        schema_version=2,
        environment_id=settings.release.environment_id,
        account_id=settings.release.account_id,
        profile="BINANCE_LIVE_WRITE",
        live_write_build_capability="QUALIFIED",
        runtime_real_write_gate=gate,
        build_manifest_digest=MANIFEST_DIGEST,
        effective_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
    )


def _currently_effective_binding(settings, *, gate: str) -> LiveWriteGateBinding:
    now = datetime.now(UTC)
    return _binding(settings, gate=gate).model_copy(
        update={
            "effective_at": now - timedelta(minutes=1),
            "expires_at": now + timedelta(hours=1),
        }
    )


def _write_binding(settings, binding: LiveWriteGateBinding) -> None:
    path = Path(str(settings.release.live_write_gate_path))
    path.write_text(
        json.dumps(binding.model_dump(mode="json")),
        encoding="utf-8",
    )


class _Result:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _Connection:
    def __init__(self, *, activation_ids: tuple[str, ...] = ("activation-live-001",)):
        self._activation_ids = activation_ids

    def execute(self, query: str, _parameters):
        assert "plan_activation" in query

        class _Rows:
            def __init__(self, activation_ids: tuple[str, ...]):
                self._activation_ids = activation_ids

            def fetchall(self):
                return [(activation_id,) for activation_id in self._activation_ids]

        return _Rows(self._activation_ids)


@pytest.fixture
def qualified_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "halpha.live_write_gate._manifest_assessment",
        lambda _repo_root, _settings: (MANIFEST_DIGEST, True, []),
    )
    monkeypatch.setattr(
        "halpha.live_write_gate.assert_live_write_gate_security",
        lambda _path, _settings: None,
    )
    monkeypatch.setattr(
        "halpha.live_write_gate.assert_live_write_gate_directory_security",
        lambda _path, _settings: None,
    )


def test_closed_binding_separates_build_identity_and_runtime_switch(
    tmp_path: Path,
    qualified_manifest: None,
) -> None:
    settings = _settings(tmp_path)
    _write_binding(settings, _binding(settings, gate="CLOSED"))

    status = evaluate_live_write_gate(ROOT, settings, now=NOW)

    assert status.live_write_build_capability == "QUALIFIED"
    assert status.configured_runtime_real_write_gate == "CLOSED"
    assert status.runtime_real_write_gate == "CLOSED"
    assert status.authorized_activation_id is None


def test_legacy_authorization_field_is_rejected_fail_closed(
    tmp_path: Path,
    qualified_manifest: None,
) -> None:
    settings = _settings(tmp_path)
    payload = _binding(settings, gate="CLOSED").model_dump(mode="json")
    payload["user_authorization_ref"] = "legacy-owner-decision"
    Path(str(settings.release.live_write_gate_path)).write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    status = evaluate_live_write_gate(ROOT, settings, now=NOW)

    assert status.live_write_build_capability == "QUALIFIED"
    assert status.configured_runtime_real_write_gate == "CLOSED"
    assert status.runtime_real_write_gate == "CLOSED"
    assert status.violations == (
        "LIVE_WRITE_GATE_BINDING_INVALID_VALIDATIONERROR",
    )


def test_open_binding_requires_database_verification_before_becoming_effective(
    tmp_path: Path,
    qualified_manifest: None,
) -> None:
    settings = _settings(tmp_path)
    _write_binding(settings, _binding(settings, gate="OPEN"))

    precheck = require_live_write_gate_precheck(ROOT, settings, now=NOW)
    assert precheck.configured_runtime_real_write_gate == "OPEN"
    assert precheck.runtime_real_write_gate == "CLOSED"
    assert precheck.violations == ("LIVE_WRITE_DATABASE_BINDING_NOT_VERIFIED",)

    effective = require_live_write_gate_open(
        ROOT,
        settings,
        _Connection(),
        now=NOW,
    )
    assert effective.runtime_real_write_gate == "OPEN"
    assert effective.authorized_activation_id == "activation-live-001"
    assert effective.violations == ()


@pytest.mark.parametrize(
    ("activation_ids", "reason"),
    (
        ((), "LIVE_WRITE_CURRENT_ACTIVATION_MISSING"),
        (("activation-live-001", "activation-live-002"), "LIVE_WRITE_CURRENT_ACTIVATION_AMBIGUOUS"),
    ),
)
def test_open_gate_requires_exactly_one_current_plan_activation(
    tmp_path: Path,
    qualified_manifest: None,
    activation_ids: tuple[str, ...],
    reason: str,
) -> None:
    settings = _settings(tmp_path)
    _write_binding(settings, _binding(settings, gate="OPEN"))

    status = evaluate_live_write_gate(
        ROOT,
        settings,
        connection=_Connection(activation_ids=activation_ids),
        now=NOW,
    )

    assert status.runtime_real_write_gate == "CLOSED"
    assert status.authorized_activation_id is None
    assert reason in status.violations
    with pytest.raises(LiveWriteGateError, match="LIVE_WRITE_GATE_CLOSED"):
        require_live_write_gate_open(
            ROOT,
            settings,
            _Connection(activation_ids=activation_ids),
            now=NOW,
        )


def test_gate_file_requires_the_exact_protected_windows_acl(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    path = Path(str(settings.release.live_write_gate_path))
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(
        LiveWriteGateError,
        match="LIVE_WRITE_GATE_FILE_(OWNER|DACL)",
    ):
        assert_live_write_gate_security(path, settings)

    _apply_security(path, settings, directory=False)
    assert_live_write_gate_security(path, settings)
    _apply_security(path.parent, settings, directory=True)
    assert_live_write_gate_directory_security(path.parent, settings)


def test_provisioning_rejects_manifest_mismatch_before_creating_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    target = tmp_path / "not-created" / "live-write-gate.json"
    settings = settings.model_copy(
        update={
            "release": settings.release.model_copy(
                update={"live_write_gate_path": str(target)}
            )
        }
    )
    monkeypatch.setattr(
        "halpha.live_write_gate._manifest_assessment",
        lambda _repo_root, _settings: ("b" * 64, True, []),
    )
    monkeypatch.setattr(
        "halpha.live_write_gate_cli.require_process_identity",
        lambda _sid: None,
    )

    with pytest.raises(LiveWriteGateError, match="LIVE_WRITE_GATE_MANIFEST_MISMATCH"):
        provision_live_write_gate_binding(
            ROOT,
            settings,
            _currently_effective_binding(settings, gate="CLOSED"),
        )

    assert not target.parent.exists()
    assert not target.exists()


def test_provisioning_accepts_only_the_exact_closed_postcondition(
    tmp_path: Path,
    qualified_manifest: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    target = Path(str(settings.release.live_write_gate_path))
    binding = _currently_effective_binding(settings, gate="CLOSED")
    monkeypatch.setattr(
        "halpha.live_write_gate_cli.require_process_identity",
        lambda _sid: None,
    )
    monkeypatch.setattr(
        "halpha.live_write_gate_cli._apply_security",
        lambda _path, _settings, *, directory: None,
    )
    monkeypatch.setattr(
        "halpha.live_write_gate_cli.assert_live_write_gate_security",
        lambda _path, _settings: None,
    )
    monkeypatch.setattr(
        "halpha.live_write_gate_cli.assert_live_write_gate_directory_security",
        lambda _path, _settings: None,
    )

    report = provision_live_write_gate_binding(ROOT, settings, binding)

    assert report == {
        "status": "PROVISIONED",
        "configured_runtime_real_write_gate": "CLOSED",
        "runtime_real_write_gate": "CLOSED",
        "live_write_build_capability": "QUALIFIED",
        "violations": [],
    }
    assert LiveWriteGateBinding.model_validate_json(
        target.read_text(encoding="utf-8")
    ) == binding


def test_provisioning_open_remains_effectively_closed_until_database_recheck(
    tmp_path: Path,
    qualified_manifest: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    binding = _currently_effective_binding(settings, gate="OPEN")
    monkeypatch.setattr(
        "halpha.live_write_gate_cli.require_process_identity",
        lambda _sid: None,
    )
    monkeypatch.setattr(
        "halpha.live_write_gate_cli._apply_security",
        lambda _path, _settings, *, directory: None,
    )
    monkeypatch.setattr(
        "halpha.live_write_gate_cli.assert_live_write_gate_security",
        lambda _path, _settings: None,
    )
    monkeypatch.setattr(
        "halpha.live_write_gate_cli.assert_live_write_gate_directory_security",
        lambda _path, _settings: None,
    )

    report = provision_live_write_gate_binding(ROOT, settings, binding)

    assert report["configured_runtime_real_write_gate"] == "OPEN"
    assert report["runtime_real_write_gate"] == "CLOSED"
    assert report["violations"] == ["LIVE_WRITE_DATABASE_BINDING_NOT_VERIFIED"]
