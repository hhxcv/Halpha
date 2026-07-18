"""Manifest-driven file evidence storage around one ParquetDataCatalog root."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
from typing import Any
import zipfile

from halpha.configuration import MaintenanceConfig


EVIDENCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,95}$")


class EvidenceStoreError(RuntimeError):
    """Fail-closed file evidence operation error."""


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_digest(value: dict[str, Any]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


class RebuildableEvidenceStore:
    def __init__(self, repository_root: Path, config: MaintenanceConfig) -> None:
        self._root = repository_root.resolve()
        self._raw_root = self._resolve_root(config.evidence_raw_root)
        self._catalog_root = self._resolve_root(config.evidence_catalog_root)
        self._report_root = self._resolve_root(config.evidence_report_root)

    def _resolve_root(self, relative: str) -> Path:
        path = (self._root / relative).resolve()
        if not path.is_relative_to(self._root):
            raise EvidenceStoreError("EVIDENCE_ROOT_OUTSIDE_REPOSITORY")
        return path

    def _identity_path(self, root: Path, evidence_id: str) -> Path:
        if EVIDENCE_ID_PATTERN.fullmatch(evidence_id) is None:
            raise EvidenceStoreError("EVIDENCE_ID_INVALID")
        path = (root / evidence_id).resolve()
        if not path.is_relative_to(root):
            raise EvidenceStoreError("EVIDENCE_ID_PATH_ESCAPE")
        return path

    def _manifest_path(self, evidence_id: str) -> Path:
        return self._identity_path(self._report_root, evidence_id).with_suffix(".json")

    def import_raw(
        self,
        source: Path,
        *,
        evidence_id: str,
        source_kind: str,
        source_ref: str,
    ) -> dict[str, Any]:
        input_path = source.resolve()
        if not input_path.is_file() or input_path.is_symlink():
            raise EvidenceStoreError("EVIDENCE_SOURCE_FILE_REQUIRED")
        destination_dir = self._identity_path(self._raw_root, evidence_id)
        manifest_path = self._manifest_path(evidence_id)
        if destination_dir.exists() or manifest_path.exists():
            raise EvidenceStoreError("EVIDENCE_ID_ALREADY_EXISTS")
        destination_dir.mkdir(parents=True)
        destination = destination_dir / input_path.name
        shutil.copyfile(input_path, destination)
        digest = _sha256_file(destination)
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "evidence_id": evidence_id,
            "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "source_kind": source_kind,
            "source_ref": source_ref,
            "raw_file": destination.name,
            "raw_size": destination.stat().st_size,
            "raw_sha256": digest,
            "catalog_implementation": (
                "nautilus_trader.persistence.catalog.ParquetDataCatalog"
            ),
            "catalog_rebuild_status": "NOT_BUILT",
            "retention": "OWNER_EXPLICIT_DELETE_ONLY",
        }
        manifest["manifest_digest"] = _canonical_digest(manifest)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return manifest

    def verify(self, evidence_id: str) -> dict[str, Any]:
        manifest_path = self._manifest_path(evidence_id)
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            raise EvidenceStoreError("EVIDENCE_MANIFEST_INVALID") from None
        raw = self._identity_path(self._raw_root, evidence_id) / str(manifest.get("raw_file"))
        recorded_digest = manifest.pop("manifest_digest", None)
        if recorded_digest != _canonical_digest(manifest):
            raise EvidenceStoreError("EVIDENCE_MANIFEST_DIGEST_MISMATCH")
        manifest["manifest_digest"] = recorded_digest
        if not raw.is_file() or _sha256_file(raw) != manifest.get("raw_sha256"):
            raise EvidenceStoreError("EVIDENCE_RAW_DIGEST_MISMATCH")
        return manifest

    def rebuild_catalog(
        self,
        evidence_id: str,
        builder: Callable[[Path, Path], None],
    ) -> dict[str, Any]:
        manifest = self.verify(evidence_id)
        raw = self._identity_path(self._raw_root, evidence_id) / manifest["raw_file"]
        catalog = self._identity_path(self._catalog_root, evidence_id)
        if catalog.exists():
            if not catalog.is_relative_to(self._catalog_root):
                raise EvidenceStoreError("EVIDENCE_CATALOG_PATH_ESCAPE")
            shutil.rmtree(catalog)
        catalog.mkdir(parents=True)
        try:
            builder(raw, catalog)
        except Exception as exc:
            shutil.rmtree(catalog, ignore_errors=True)
            raise EvidenceStoreError(
                f"EVIDENCE_CATALOG_REBUILD_FAILED type={type(exc).__name__}"
            ) from None
        inventory = sorted(
            (
                {
                "path": path.relative_to(catalog).as_posix(),
                "sha256": _sha256_file(path),
                }
                for path in catalog.rglob("*")
                if path.is_file()
            ),
            key=lambda item: item["path"],
        )
        manifest["catalog_rebuild_status"] = "BUILT"
        manifest["catalog_inventory"] = inventory
        manifest["manifest_digest"] = _canonical_digest(
            {key: value for key, value in manifest.items() if key != "manifest_digest"}
        )
        self._manifest_path(evidence_id).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return manifest

    def export(self, evidence_id: str, destination: Path) -> Path:
        manifest = self.verify(evidence_id)
        output = destination.resolve()
        if output.suffix.casefold() != ".zip":
            raise EvidenceStoreError("EVIDENCE_EXPORT_ZIP_REQUIRED")
        output.parent.mkdir(parents=True, exist_ok=True)
        raw = self._identity_path(self._raw_root, evidence_id) / manifest["raw_file"]
        with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(raw, f"raw/{raw.name}")
            archive.write(self._manifest_path(evidence_id), "manifest.json")
            archive.writestr("SHA256SUMS", f"{manifest['raw_sha256']}  raw/{raw.name}\n")
        return output

    def delete(self, evidence_id: str, *, expected_manifest_digest: str) -> None:
        manifest = self.verify(evidence_id)
        if manifest["manifest_digest"] != expected_manifest_digest:
            raise EvidenceStoreError("EVIDENCE_DELETE_DIGEST_MISMATCH")
        for root in (self._raw_root, self._catalog_root):
            path = self._identity_path(root, evidence_id)
            if path.exists():
                if not path.is_relative_to(root):
                    raise EvidenceStoreError("EVIDENCE_DELETE_PATH_ESCAPE")
                shutil.rmtree(path)
        self._manifest_path(evidence_id).unlink()
