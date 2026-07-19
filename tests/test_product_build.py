from __future__ import annotations

from pathlib import Path

from halpha.configuration import load_settings
from halpha.product_build import (
    PRODUCT_BUILD_INPUT_PATTERNS,
    calculate_product_build_id,
)


ROOT = Path(__file__).resolve().parents[1]


def _product_tree(root: Path) -> None:
    files = {
        "pyproject.toml": "[project]\nname='test'\n",
        "requirements/runtime.txt": "runtime==1\n",
        "frontend/package-lock.json": "{}\n",
        "frontend/dist/index.html": "<main>Halpha</main>\n",
        "src/halpha/app.py": "VALUE = 1\n",
        "src/halpha/planning/strategy_registry.json": "{}\n",
        "migrations/versions/current.py": "revision = 'current'\n",
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def test_product_build_id_is_stable_and_ignores_non_product_files(
    tmp_path: Path,
) -> None:
    _product_tree(tmp_path)
    settings = load_settings(ROOT / "config" / "halpha.example.toml")
    first = calculate_product_build_id(tmp_path, settings)

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "note.md").write_text("not a runtime input", encoding="utf-8")
    assert calculate_product_build_id(tmp_path, settings) == first

    (tmp_path / "src" / "halpha" / "app.py").write_text(
        "VALUE = 2\n", encoding="utf-8"
    )
    assert calculate_product_build_id(tmp_path, settings) != first


def test_effective_nonsecret_configuration_changes_product_build_id(
    tmp_path: Path,
) -> None:
    _product_tree(tmp_path)
    settings = load_settings(ROOT / "config" / "halpha.example.toml")
    changed = settings.model_copy(
        update={
            "release": settings.release.model_copy(
                update={"environment_id": "binance-demo-secondary"}
            )
        }
    )

    assert calculate_product_build_id(tmp_path, settings) != calculate_product_build_id(
        tmp_path, changed
    )


def test_product_build_inputs_exclude_git_tests_docs_and_qualification_reports() -> None:
    joined = "\n".join(PRODUCT_BUILD_INPUT_PATTERNS)
    assert ".git" not in joined
    assert "tests" not in joined
    assert "docs" not in joined
    assert "tools" not in joined
    assert "build/evidence" not in joined
