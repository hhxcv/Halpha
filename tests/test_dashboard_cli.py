from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from halpha.cli import main
from halpha.config import load_config
from halpha.dashboard import create_dashboard_app, dashboard_health


def test_dashboard_help_mentions_local_server(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["dashboard", "--help"])

    output = capsys.readouterr().out
    assert exc.value.code == 0
    assert "Run the local web dashboard." in output
    assert "--config" in output
    assert "--host" in output
    assert "--port" in output


def test_dashboard_health_endpoint_uses_bounded_config_ref() -> None:
    config_path = Path("config.example.yaml")
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["artifact_type"] == "dashboard_health"
    assert payload["service"] == "halpha_dashboard"
    assert payload["status"] == "ok"
    assert payload["local_only"] is True
    assert payload["host"] == "127.0.0.1"
    assert payload["port"] == 8765
    assert payload["config"] == {"loaded": True, "ref": "config.example.yaml"}
    assert payload["features"]["overview_api"] == "not_implemented"


def test_dashboard_health_omits_external_absolute_config_path(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    payload = dashboard_health(config, config_path=config_path)

    assert payload["config"] == {"loaded": True, "ref": "<external-config>"}
    assert str(tmp_path) not in str(payload)


def test_dashboard_command_loads_config_and_invokes_service(
    tmp_path: Path,
    capsys,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    calls: list[dict[str, object]] = []

    def fake_run_dashboard_service(config, *, config_path, host, port):  # noqa: ANN001
        calls.append(
            {
                "config": config,
                "config_path": config_path,
                "host": host,
                "port": port,
            }
        )

    monkeypatch.setattr("halpha.cli.run_dashboard_service", fake_run_dashboard_service)

    exit_code = main(
        [
            "dashboard",
            "--config",
            str(config_path),
            "--host",
            "localhost",
            "--port",
            "9001",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Halpha dashboard starting." in output
    assert "url: http://localhost:9001" in output
    assert "config: <external-config>" in output
    assert str(tmp_path) not in output
    assert len(calls) == 1
    assert calls[0]["config_path"] == config_path
    assert calls[0]["host"] == "localhost"
    assert calls[0]["port"] == 9001


def test_dashboard_rejects_non_local_host_before_service_start(
    tmp_path: Path,
    capsys,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)

    def fail_service(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("invalid dashboard host must not start the service")

    monkeypatch.setattr("halpha.cli.run_dashboard_service", fail_service)

    exit_code = main(["dashboard", "--config", str(config_path), "--host", "0.0.0.0"])

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "Halpha dashboard failed." in output
    assert "stage: dashboard" in output
    assert "dashboard host must be local-only" in output
    assert "Halpha dashboard starting." not in output
    assert str(tmp_path) not in output


def test_dashboard_config_error_omits_external_absolute_path(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "missing.yaml"

    exit_code = main(["dashboard", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "Halpha dashboard failed." in output
    assert "stage: config" in output
    assert "config file not found: <external-config>" in output
    assert str(tmp_path) not in output


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
run:
  output_dir: runs
market:
  enabled: false
text:
  enabled: false
  sources: []
report:
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return path
