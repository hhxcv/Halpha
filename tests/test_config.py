from pathlib import Path

import pytest

from halpha.config import ConfigError, load_config


def test_config_example_loads_successfully() -> None:
    config = load_config(Path("config.example.yaml"))

    assert config["run"]["output_dir"] == "runs"
    assert config["market"]["source"] == "binance"
    assert config["market"]["symbols"] == ["BTCUSDT", "ETHUSDT"]
    assert config["text"]["sources"][0]["type"] == "rss"
    assert config["report"]["language"] == "zh-CN"


def test_load_config_rejects_non_mapping_root(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("- run\n- market\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="config root must be a mapping"):
        load_config(config_path)


@pytest.mark.parametrize("section", ["run", "market", "text", "report", "codex"])
def test_load_config_rejects_non_mapping_sections(tmp_path: Path, section: str) -> None:
    config_path = _write_valid_config(tmp_path)
    section_blocks = {
        "run": "run:\n  output_dir: runs",
        "market": "market:\n  enabled: true\n  source: binance\n  symbols:\n    - BTCUSDT",
        "text": (
            "text:\n"
            "  enabled: true\n"
            "  sources:\n"
            "    - name: coindesk\n"
            "      type: rss\n"
            "      url: https://www.coindesk.com/arc/outboundfeeds/rss/"
        ),
        "report": "report:\n  language: zh-CN",
        "codex": (
            "codex:\n"
            "  enabled: true\n"
            "  command: codex\n"
            "  args:\n"
            "    - exec\n"
            "    - --sandbox\n"
            "    - read-only\n"
            "    - \"-\"\n"
            "  timeout_seconds: 300"
        ),
    }
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(section_blocks[section], f"{section}: invalid"),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=f"{section} must be a mapping"):
        load_config(config_path)


def test_load_config_rejects_product_local_file_inputs_as_unsupported_section(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    config_text = config_path.read_text(encoding="utf-8")
    config_path.write_text(
        f"""
inputs:
  market_file: tests/fixtures/raw_market.json
  public_info_file: tests/fixtures/raw_text_events.json
{config_text}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="unsupported top-level config section\\(s\\): inputs"):
        load_config(config_path)


def test_load_config_rejects_unknown_top_level_section(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    config_text = config_path.read_text(encoding="utf-8")
    config_path.write_text(
        f"""
profiles:
  local: true
{config_text}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="unsupported top-level config section"):
        load_config(config_path)


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ("run:\n  output_dir: runs", "run: {}", "run.output_dir"),
        ("  source: binance", "", "market.source"),
        ("  symbols:\n    - BTCUSDT", "", "market.symbols"),
        (
            "  sources:\n    - name: coindesk\n      type: rss\n      url: https://www.coindesk.com/arc/outboundfeeds/rss/",
            "",
            "text.sources",
        ),
        ("  command: codex", "", "codex.command"),
        ("  args:\n    - exec\n    - --sandbox\n    - read-only\n    - \"-\"", "", "codex.args"),
        ("  timeout_seconds: 300", "", "codex.timeout_seconds"),
    ],
)
def test_load_config_rejects_missing_required_fields(
    tmp_path: Path, old: str, new: str, expected: str
) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(old, new),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=expected):
        load_config(config_path)


def test_load_config_accepts_source_based_online_collection_contract(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        .replace("source: binance", "source: public_market_api")
        .replace("type: rss", "type: public_feed"),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config["market"]["source"] == "public_market_api"
    assert config["text"]["sources"][0]["type"] == "public_feed"


def test_load_config_rejects_local_text_source_url(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "https://www.coindesk.com/arc/outboundfeeds/rss/",
            "tests/fixtures/feed.xml",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=r"text\.sources\[0\]\.url"):
        load_config(config_path)


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ("enabled: true", "enabled: \"yes\"", "market.enabled"),
        ("enabled: true", "enabled: \"yes\"", "text.enabled"),
        ("enabled: true", "enabled: \"yes\"", "codex.enabled"),
        ("source: binance", "source: 123", "market.source"),
        ("- BTCUSDT", "- 123", r"market\.symbols\[0\]"),
        ("name: coindesk", "name: 123", r"text\.sources\[0\]\.name"),
        ("type: rss", "type: 123", r"text\.sources\[0\]\.type"),
        ("url: https://www.coindesk.com/arc/outboundfeeds/rss/", "url: 123", r"text\.sources\[0\]\.url"),
        ("command: codex", "command: 123", "codex.command"),
        ("- exec", "- 123", r"codex\.args\[0\]"),
    ],
)
def test_load_config_rejects_invalid_field_types(
    tmp_path: Path, old: str, new: str, expected: str
) -> None:
    config_path = _write_valid_config(tmp_path)
    text = config_path.read_text(encoding="utf-8")
    if expected == "text.enabled":
        text = text.replace("text:\n  enabled: true", "text:\n  enabled: \"yes\"")
    elif expected == "codex.enabled":
        text = text.replace("codex:\n  enabled: true", "codex:\n  enabled: \"yes\"")
    else:
        text = text.replace(old, new, 1)
    config_path.write_text(text, encoding="utf-8")

    with pytest.raises(ConfigError, match=expected):
        load_config(config_path)


def test_load_config_rejects_invalid_text_max_items(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "text:\n  enabled: true",
            "text:\n  enabled: true\n  max_items: 0",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="text.max_items"):
        load_config(config_path)


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ("text:\n  enabled: true", "text:\n  enabled: true\n  max_items: true", "text.max_items"),
        ("timeout_seconds: 300", "timeout_seconds: true", "codex.timeout_seconds"),
    ],
)
def test_load_config_rejects_boolean_positive_integer_fields(
    tmp_path: Path, old: str, new: str, expected: str
) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(old, new),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=expected):
        load_config(config_path)


def _write_valid_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  output_dir: runs
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
text:
  enabled: true
  sources:
    - name: coindesk
      type: rss
      url: https://www.coindesk.com/arc/outboundfeeds/rss/
report:
  language: zh-CN
codex:
  enabled: true
  command: codex
  args:
    - exec
    - --sandbox
    - read-only
    - "-"
  timeout_seconds: 300
""".strip(),
        encoding="utf-8",
    )
    return config_path
