import json
from pathlib import Path

from halpha.text import text_models
from halpha.cli import main


def test_prepare_text_models_records_skipped_metadata_without_downloads(tmp_path: Path) -> None:
    result = text_models.prepare_text_models(
        _config(),
        output_dir=tmp_path / "models",
        now="2026-01-01T00:00:00Z",
    )

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    serialized = json.dumps(manifest, ensure_ascii=False)

    assert result.succeeded
    assert result.status == "skipped"
    assert manifest["status"] == "skipped"
    assert manifest["download_policy"] == {"allow_model_download": False}
    assert manifest["coverage"] == {
        "models": 4,
        "succeeded": 0,
        "skipped": 4,
        "degraded": 0,
        "failed": 0,
        "unavailable": 0,
    }
    assert sorted(state["role"] for state in manifest["model_states"]) == [
        "classifier",
        "embedding",
        "ner",
        "sentiment",
    ]
    assert all(state["status"] == "skipped" for state in manifest["model_states"])
    assert all("model_download_disabled" in state["warnings"] for state in manifest["model_states"])
    assert "model_cache_dir" not in manifest
    assert str(tmp_path) not in serialized


def test_prepare_text_models_records_unavailable_when_download_dependency_is_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(text_models, "_snapshot_download", lambda: None)
    config = _config(allow_model_download=True, revision="abc123")

    result = text_models.prepare_text_models(config, output_dir=tmp_path / "models")

    assert not result.succeeded
    assert result.exit_code == 1
    assert result.status == "failed"
    assert result.manifest["coverage"]["unavailable"] == 4
    assert 'python -m pip install -e ".[nlp]"' in result.manifest["errors"][0]


def test_prepare_text_models_uses_runtime_root_for_configured_model_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    config_dir = tmp_path / "external-config"
    runtime_root.mkdir()
    config_dir.mkdir()
    monkeypatch.chdir(runtime_root)
    config_path = config_dir / "config.yaml"
    config_path.write_text(_config_yaml(), encoding="utf-8")

    result = text_models.prepare_text_models(
        _config(),
        config_path=config_path,
        now="2026-01-01T00:00:00Z",
    )

    assert result.succeeded
    assert result.manifest_path == runtime_root / "data" / "models" / "text" / text_models.TEXT_MODEL_PREPARE_MANIFEST
    assert result.manifest_path.exists()
    assert not (config_dir / "data").exists()


def test_text_models_prepare_cli_writes_manifest_without_optional_nlp_dependencies(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = tmp_path / "config.yaml"
    output_dir = tmp_path / "prepared"
    config_path.write_text(_config_yaml(), encoding="utf-8")

    exit_code = main(
        [
            "text-models",
            "prepare",
            "--config",
            str(config_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    stdout = capsys.readouterr().out
    manifest_path = output_dir / text_models.TEXT_MODEL_PREPARE_MANIFEST

    assert exit_code == 0
    assert "Halpha text model preparation completed." in stdout
    assert "status: skipped" in stdout
    expected_manifest = manifest_path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    assert f"manifest: {expected_manifest}" in stdout
    assert manifest_path.exists()


def _config(*, allow_model_download: bool = False, revision: str = "pinned") -> dict:
    return {
        "text": {
            "enabled": True,
            "intelligence": {
                "enabled": True,
                "model_cache_dir": "data/models/text",
                "allow_model_download": allow_model_download,
                "models": {
                    "embedding": {
                        "provider": "sentence_transformers",
                        "name": "sentence-transformers/all-MiniLM-L6-v2",
                        "revision": revision,
                    },
                    "classifier": {
                        "provider": "transformers_zero_shot",
                        "name": "facebook/bart-large-mnli",
                        "revision": revision,
                    },
                    "sentiment": {
                        "provider": "transformers_text_classification",
                        "name": "ProsusAI/finbert",
                        "revision": revision,
                    },
                    "ner": {
                        "provider": "gliner",
                        "name": "urchade/gliner_medium-v2.1",
                        "revision": revision,
                    },
                },
                "thresholds": {
                    "duplicate_similarity": 0.92,
                    "same_topic_similarity": 0.82,
                    "classifier_accept_score": 0.65,
                    "classifier_top_margin": 0.10,
                    "entity_accept_score": 0.50,
                    "max_topic_window_hours": 48,
                },
            },
        },
    }


def _config_yaml() -> str:
    return """
run:
  output_dir: runs
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
  ohlcv:
    storage_dir: data/market/ohlcv
    timeframes:
      - 1d
      - 1h
    lookback:
      1d: 500
      1h: 720
quant:
  enabled: false
text:
  enabled: true
  intelligence:
    enabled: true
    model_cache_dir: data/models/text
    allow_model_download: false
    models:
      embedding:
        provider: sentence_transformers
        name: sentence-transformers/all-MiniLM-L6-v2
        revision: pinned
      classifier:
        provider: transformers_zero_shot
        name: facebook/bart-large-mnli
        revision: pinned
      sentiment:
        provider: transformers_text_classification
        name: ProsusAI/finbert
        revision: pinned
      ner:
        provider: gliner
        name: urchade/gliner_medium-v2.1
        revision: pinned
    thresholds:
      duplicate_similarity: 0.92
      same_topic_similarity: 0.82
      classifier_accept_score: 0.65
      classifier_top_margin: 0.10
      entity_accept_score: 0.50
      max_topic_window_hours: 48
  sources:
    - name: coindesk
      type: rss
      url: https://www.coindesk.com/arc/outboundfeeds/rss/
report:
  language: zh-CN
codex:
  enabled: false
""".strip()
