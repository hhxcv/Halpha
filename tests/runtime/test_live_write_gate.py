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
    refs = (
        {
            "account_capital_limit_version_ref": "limit-live-001",
            "machine_authorization_version_ref": "authorization-live-001",
            "plan_allocation_ref": "allocation-live-001",
        }
        if gate == "OPEN"
        else {}
    )
    return LiveWriteGateBinding(
        schema_version=1,
        environment_id=settings.release.environment_id,
        account_id=settings.release.account_id,
        profile="BINANCE_LIVE_WRITE",
        live_write_build_capability="QUALIFIED",
        b05_package_eligibility="AUTHORIZED",
        runtime_real_write_gate=gate,
        build_manifest_digest=MANIFEST_DIGEST,
        user_authorization_ref="owner-decision:b05-live-001",
        effective_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
        **refs,
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
    def __init__(self, settings, *, acknowledgements: bool = True):
        self._settings = settings
        self._acknowledgements = acknowledgements

    def execute(self, query: str, _parameters):
        if "account_capital_limit_version" in query:
            row = (
                "LIVE",
                "LIVE_REAL_CAPITAL",
                self._settings.release.account_id,
                {"instruments": ["BTCUSDT-PERP"]},
            )
        elif "machine_authorization_version" in query:
            row = (
                "activation-live-001",
                "plan-version-live-001",
                "LIVE",
                "LIVE_REAL_CAPITAL",
                self._settings.release.account_id,
                "BTCUSDT-PERP",
                NOW - timedelta(minutes=2),
                NOW + timedelta(hours=2),
                {
                    "real_capital_acknowledged": self._acknowledgements,
                    "evidence_limitations_acknowledged": self._acknowledgements,
                    "online_monitoring_acknowledged": self._acknowledgements,
                },
            )
        elif "plan_allocation" in query:
            row = (
                "activation-live-001",
                "limit-live-001",
                "LIVE",
                "LIVE_REAL_CAPITAL",
                "HELD",
            )
        elif "plan_activation" in query:
            row = (
                "plan-version-live-001",
                "authorization-live-001",
                "allocation-live-001",
                "LIVE",
                "LIVE_REAL_CAPITAL",
                self._settings.release.account_id,
                "BTCUSDT-PERP",
                "RUNNING",
                "ACTIVE",
            )
        else:
            raise AssertionError(query)
        return _Result(row)


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


def test_closed_binding_separates_build_package_and_runtime_gate(
    tmp_path: Path,
    qualified_manifest: None,
) -> None:
    settings = _settings(tmp_path)
    _write_binding(settings, _binding(settings, gate="CLOSED"))

    status = evaluate_live_write_gate(ROOT, settings, now=NOW)

    assert status.live_write_build_capability == "QUALIFIED"
    assert status.b05_package_eligibility == "AUTHORIZED"
    assert status.configured_runtime_real_write_gate == "CLOSED"
    assert status.runtime_real_write_gate == "CLOSED"
    assert status.authorized_activation_id is None


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
        _Connection(settings),
        now=NOW,
    )
    assert effective.runtime_real_write_gate == "OPEN"
    assert effective.authorized_activation_id == "activation-live-001"
    assert effective.violations == ()


def test_owner_acknowledgements_are_rechecked_from_machine_authorization(
    tmp_path: Path,
    qualified_manifest: None,
) -> None:
    settings = _settings(tmp_path)
    _write_binding(settings, _binding(settings, gate="OPEN"))

    status = evaluate_live_write_gate(
        ROOT,
        settings,
        connection=_Connection(settings, acknowledgements=False),
        now=NOW,
    )

    assert status.runtime_real_write_gate == "CLOSED"
    assert status.authorized_activation_id is None
    assert "LIVE_WRITE_OWNER_ACKNOWLEDGEMENTS_MISSING" in status.violations
    with pytest.raises(LiveWriteGateError, match="LIVE_WRITE_GATE_CLOSED"):
        require_live_write_gate_open(
            ROOT,
            settings,
            _Connection(settings, acknowledgements=False),
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
        "b05_package_eligibility": "AUTHORIZED",
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
