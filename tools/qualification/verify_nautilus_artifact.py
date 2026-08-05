from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
from zipfile import ZipFile


EXPECTED_FILENAME = "nautilus_trader-1.230.0-cp313-cp313-win_amd64.whl"
EXPECTED_SHA256 = "8817c46dc34e0aafc606948aacf1dd0fbbe1a31273c8a2f20983cf4ab2ddeef1"
EXPECTED_VERSION = "1.230.0"
EXPECTED_TAG = "cp313-cp313-win_amd64"
EXPECTED_TAG_OBJECT_SHA = "112d335088ec11cdd1d60038b16c8fe56406aead"
EXPECTED_COMMIT_SHA = "8160730c7c550480b0a439fb11086a4c4de15f0b"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path, required=True)
    args = parser.parse_args()

    errors: list[str] = []
    wheel = args.wheel.resolve()
    actual_hash = _sha256(wheel)
    if wheel.name != EXPECTED_FILENAME:
        errors.append("WHEEL_FILENAME_MISMATCH")
    if actual_hash != EXPECTED_SHA256:
        errors.append("WHEEL_SHA256_MISMATCH")

    wheel_tag = "UNAVAILABLE"
    bundled_license = False
    with ZipFile(wheel) as archive:
        wheel_metadata = archive.read("nautilus_trader-1.230.0.dist-info/WHEEL").decode("utf-8")
        for line in wheel_metadata.splitlines():
            if line.startswith("Tag: "):
                wheel_tag = line.removeprefix("Tag: ").strip()
        license_text = archive.read(
            "nautilus_trader-1.230.0.dist-info/licenses/LICENSE",
        ).decode("utf-8", errors="replace")
        bundled_license = (
            "GNU LESSER GENERAL PUBLIC LICENSE" in license_text
            and "Version 3" in license_text
        )
    if wheel_tag != EXPECTED_TAG:
        errors.append("WHEEL_TAG_MISMATCH")
    if not bundled_license:
        errors.append("BUNDLED_LICENSE_MISMATCH")

    metadata = importlib.metadata.metadata("nautilus-trader")
    installed_version = importlib.metadata.version("nautilus-trader")
    installed_license = metadata.get("License", "")
    if installed_version != EXPECTED_VERSION:
        errors.append("INSTALLED_VERSION_MISMATCH")
    if installed_license != "LGPL-3.0-or-later":
        errors.append("INSTALLED_LICENSE_MISMATCH")

    evidence = {
        "wheel_filename": wheel.name,
        "wheel_sha256": actual_hash,
        "wheel_tag": wheel_tag,
        "installed_version": installed_version,
        "installed_license": installed_license,
        "bundled_license_present": bundled_license,
        "source_tag": "v1.230.0",
        "source_tag_object_sha": EXPECTED_TAG_OBJECT_SHA,
        "source_commit_sha": EXPECTED_COMMIT_SHA,
        "errors": errors,
        "status": "QUALIFIED" if not errors else "REJECTED",
    }
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
