from __future__ import annotations

from pathlib import Path

from halpha.dashboard.data_cleanup import dashboard_data_deletion_plan, dashboard_delete_data


def test_dashboard_data_cleanup_requires_run_artifact_confirmation(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    config = {"run": {"output_dir": "runs"}}
    runs_payload = {
        "status": "available",
        "runs": [{"run_id": "run-1", "run_dir": "runs/run-1", "status": "succeeded"}],
        "warnings": [],
        "errors": [],
    }
    stores_payload = {"status": "available", "stores": [], "warnings": [], "errors": []}

    result = dashboard_delete_data(
        config,
        config_path=tmp_path / "config.local.yaml",
        request={"kind": "run_artifacts", "run_ids": ["run-1"], "confirm": "DELETE"},
        runs_payload=runs_payload,
        stores_payload=stores_payload,
    )

    assert result["status"] == "blocked"
    assert run_dir.exists()


def test_dashboard_data_cleanup_blocks_external_shared_refs(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    external_storage_dir = project_root.parent / "external_ohlcv"
    config = {
        "run": {"output_dir": "runs"},
        "market": {"ohlcv": {"storage_dir": str(external_storage_dir)}},
    }
    runs_payload = {"status": "available", "runs": [], "warnings": [], "errors": []}
    stores_payload = {
        "status": "available",
        "stores": [
            {
                "name": "ohlcv_history",
                "title": "OHLCV history",
                "status": "available",
                "fields": {"records": 10},
                "warnings": [],
                "errors": [],
            }
        ],
        "warnings": [],
        "errors": [],
    }

    plan = dashboard_data_deletion_plan(
        config,
        config_path=tmp_path / "config.local.yaml",
        runs_payload=runs_payload,
        stores_payload=stores_payload,
    )

    shared = plan["shared_data"]["items"][0]
    assert shared["deletable"] is False
    assert shared["blocked_reason"] == "one or more refs are outside the shared-data deletion boundary."
    assert any(record["ref"] == "<external-artifact>" for record in shared["delete_refs"])
    assert str(external_storage_dir) not in str(plan)
