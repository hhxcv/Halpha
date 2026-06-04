from pathlib import Path

import pytest

from halpha.config import ConfigError, load_config


def test_load_config_rejects_missing_market_symbols(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  output_dir: runs
market:
  enabled: true
  source: binance
text:
  enabled: false
report:
  language: zh-CN
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="market.symbols"):
        load_config(config_path)
