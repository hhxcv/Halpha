from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest

from halpha.configuration import load_settings
from halpha.evidence_store import EvidenceStoreError, RebuildableEvidenceStore


ROOT = Path(__file__).resolve().parents[2]


def _store(tmp_path: Path) -> RebuildableEvidenceStore:
    settings = load_settings(ROOT / "config" / "halpha.example.toml")
    config = settings.maintenance.model_copy(
        update={
            "evidence_raw_root": "runtime/raw",
            "evidence_catalog_root": "runtime/catalog",
            "evidence_report_root": "runtime/reports",
        }
    )
    return RebuildableEvidenceStore(tmp_path, config)


def test_import_verify_rebuild_export_and_digest_gated_delete(tmp_path: Path) -> None:
    source = tmp_path / "BTCUSDT-1m.csv"
    source.write_text("open_time,open,high,low,close,volume\n", encoding="utf-8")
    store = _store(tmp_path)
    manifest = store.import_raw(
        source,
        evidence_id="btc-demo-1m",
        source_kind="BINANCE_USDM_CONTRACT_BAR",
        source_ref="binance-public-data",
    )
    assert store.verify("btc-demo-1m")["raw_sha256"] == manifest["raw_sha256"]

    rebuilt = store.rebuild_catalog(
        "btc-demo-1m",
        lambda raw, catalog: (catalog / "bars.parquet").write_bytes(raw.read_bytes()),
    )
    assert rebuilt["catalog_rebuild_status"] == "BUILT"
    assert rebuilt["catalog_inventory"][0]["path"] == "bars.parquet"

    exported = store.export("btc-demo-1m", tmp_path / "export.zip")
    with zipfile.ZipFile(exported) as archive:
        assert set(archive.namelist()) == {
            "raw/BTCUSDT-1m.csv",
            "manifest.json",
            "SHA256SUMS",
        }

    with pytest.raises(EvidenceStoreError, match="DELETE_DIGEST_MISMATCH"):
        store.delete("btc-demo-1m", expected_manifest_digest="0" * 64)
    current = store.verify("btc-demo-1m")
    store.delete("btc-demo-1m", expected_manifest_digest=current["manifest_digest"])
    with pytest.raises(EvidenceStoreError, match="MANIFEST_INVALID"):
        store.verify("btc-demo-1m")


def test_raw_tamper_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "bars.csv"
    source.write_text("trusted", encoding="utf-8")
    store = _store(tmp_path)
    store.import_raw(
        source,
        evidence_id="tamper-case",
        source_kind="TEST",
        source_ref="fixture",
    )
    raw = tmp_path / "runtime" / "raw" / "tamper-case" / "bars.csv"
    raw.write_text("changed", encoding="utf-8")
    with pytest.raises(EvidenceStoreError, match="RAW_DIGEST_MISMATCH"):
        store.verify("tamper-case")


def test_policy_names_single_catalog_and_git_independent_exit() -> None:
    policy = json.loads((ROOT / "config" / "evidence-storage-policy.json").read_text())
    assert policy["catalog_implementation"].endswith("ParquetDataCatalog")
    assert policy["retention"] == "OWNER_EXPLICIT_DELETE_ONLY"
    assert "WITHOUT_HALPHA_OR_POSTGRESQL" in policy["exit_rule"]
