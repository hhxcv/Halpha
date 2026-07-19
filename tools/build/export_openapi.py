"""Export the App OpenAPI document without resolving secrets or connecting externally."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pydantic import SecretStr

from halpha.app.secrets import AppSecrets
from halpha.app.web import create_app
from halpha.configuration import load_settings


class SchemaOnlyProjection:
    def overview(self) -> dict[str, Any]:
        raise AssertionError("OPENAPI_EXPORT_MUST_NOT_QUERY_PRODUCT_STATE")

    def availability(self) -> dict[str, Any]:
        raise AssertionError("OPENAPI_EXPORT_MUST_NOT_QUERY_PRODUCT_STATE")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="export_openapi")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    settings = load_settings(ROOT / "config" / "halpha.example.toml")
    app = create_app(
        settings,
        AppSecrets(
            database_password=SecretStr("schema-only-database-value"),
            csrf_signing_secret=SecretStr("schema-only-csrf-signing-value"),
        ),
        repo_root=ROOT,
        projection=SchemaOnlyProjection(),
        static_dist=ROOT / "build" / "schema-only-no-static",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "OPENAPI_EXPORTED", "output": str(args.output.resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
