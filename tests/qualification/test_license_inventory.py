from __future__ import annotations

from pathlib import Path

from tools.qualification.generate_license_inventory import generate


ROOT = Path(__file__).resolve().parents[2]


def test_complete_lock_license_inventory_passes() -> None:
    report, notices = generate(ROOT)
    assert report["status"] == "QUALIFIED"
    assert report["python"]["runtime_lock_count"] > 0
    assert report["python"]["full_dev_lock_count"] >= report["python"]["runtime_lock_count"]
    assert report["npm"]["full_lock_count"] > 0
    assert report["unknown_or_incompatible"] == []
    assert report["direct_dependencies"]["count"] == len(
        report["direct_dependencies"]["members"]
    )
    assert "nautilus-trader" in notices
    assert "@mui/material" in notices
