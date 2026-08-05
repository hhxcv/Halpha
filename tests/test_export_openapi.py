from __future__ import annotations

import json

from halpha.app import web
from tools.build import export_openapi


def test_openapi_export_does_not_require_a_built_frontend(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_if_runtime_build_identity_is_calculated(*_args, **_kwargs):
        raise AssertionError("OPENAPI_EXPORT_MUST_NOT_REQUIRE_RUNTIME_BUILD_INPUTS")

    monkeypatch.setattr(
        web,
        "calculate_product_build_id",
        fail_if_runtime_build_identity_is_calculated,
    )
    output = tmp_path / "openapi.json"

    assert export_openapi.main(["--output", str(output)]) == 0

    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["openapi"].startswith("3.")
