from pathlib import Path

import pytest

from halpha.config import ConfigError, load_config


def test_config_example_loads_successfully() -> None:
    config = load_config(Path("config.example.yaml"))

    assert config["run"]["output_dir"] == "runs"
    assert config["market"]["source"] == "binance"
    assert config["market"]["proxy"] == {"enabled": False}
    assert config["market"]["symbols"] == ["BTCUSDT", "ETHUSDT"]
    assert config["market"]["ohlcv"]["storage_dir"] == "data/market/ohlcv"
    assert config["market"]["ohlcv"]["timeframes"] == ["1d", "1h"]
    assert config["market"]["ohlcv"]["lookback"] == {"1d": 500, "1h": 720}
    assert config["quant"]["enabled"] is True
    assert config["quant"]["engine"] == "vectorbt"
    assert [strategy["name"] for strategy in config["quant"]["strategies"]] == [
        "tsmom_vol_scaled",
        "breakout_atr_trend",
        "sma_cross_trend",
        "bollinger_rsi_reversion",
    ]
    assert all(strategy["enabled"] is True for strategy in config["quant"]["strategies"])
    assert all(strategy["backtest"]["enabled"] is True for strategy in config["quant"]["strategies"])
    assert config["quant"]["strategies"][0]["params"] == {
        "return_window": 120,
        "volatility_window": 60,
        "target_volatility": 0.2,
    }
    assert config["quant"]["strategies"][1]["params"] == {
        "breakout_window": 120,
        "exit_window": 20,
        "atr_window": 14,
    }
    assert config["quant"]["strategies"][2]["params"] == {
        "short_window": 20,
        "long_window": 30,
    }
    assert config["quant"]["strategies"][3]["params"] == {
        "bollinger_window": 20,
        "band_std": 2.0,
        "rsi_window": 14,
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "trend_window": 100,
        "trend_filter_pct": 10.0,
    }
    assert config["quant"]["effectiveness_gates"] == {
        "min_positive_net_return_benchmark_pct": 25.0,
        "max_cost_drag_pct": 6.0,
        "require_walk_forward_stable": False,
        "min_walk_forward_positive_net_return_window_pct": 0.0,
    }
    assert config["quant"]["parameter_diagnostics"]["enabled"] is True
    assert config["quant"]["parameter_diagnostics"]["max_combinations"] == 16
    assert sorted(config["quant"]["parameter_diagnostics"]["grids"]) == [
        "bollinger_rsi_reversion",
        "breakout_atr_trend",
        "sma_cross_trend",
        "tsmom_vol_scaled",
    ]
    assert config["text"]["sources"][0]["type"] == "rss"
    assert config["report"]["language"] == "zh-CN"


def test_load_config_rejects_non_mapping_root(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("- run\n- market\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="config root must be a mapping"):
        load_config(config_path)


@pytest.mark.parametrize("section", ["run", "market", "quant", "text", "report", "codex"])
def test_load_config_rejects_non_mapping_sections(tmp_path: Path, section: str) -> None:
    config_path = _write_valid_config(tmp_path)
    section_blocks = {
        "run": "run:\n  output_dir: runs",
        "market": (
            "market:\n"
            "  enabled: true\n"
            "  source: binance\n"
            "  symbols:\n"
            "    - BTCUSDT\n"
            "  ohlcv:\n"
            "    storage_dir: data/market/ohlcv\n"
            "    timeframes:\n"
            "      - 1d\n"
            "      - 1h\n"
            "    lookback:\n"
            "      1d: 500\n"
            "      1h: 720"
        ),
        "quant": (
            "quant:\n"
            "  enabled: true\n"
            "  engine: vectorbt\n"
            "  strategies:\n"
            "    - name: tsmom_vol_scaled\n"
            "      enabled: true\n"
            "      params:\n"
            "        return_window: 20\n"
            "        volatility_window: 20\n"
            "        target_volatility: 0.2"
        ),
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


def test_load_config_accepts_existing_report_config_without_quant_section(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    _remove_quant_and_ohlcv(config_path)

    config = load_config(config_path)

    assert "quant" not in config
    assert "ohlcv" not in config["market"]


def test_load_config_accepts_quant_strategy_config(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)

    config = load_config(config_path)

    assert config["quant"]["engine"] == "vectorbt"
    assert config["quant"]["strategies"][0]["name"] == "tsmom_vol_scaled"


def test_load_config_accepts_enabled_parameter_diagnostics_config(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "        target_volatility: 0.2",
            (
                "        target_volatility: 0.2\n"
                "  parameter_diagnostics:\n"
                "    enabled: true\n"
                "    max_combinations: 4\n"
                "    grids:\n"
                "      tsmom_vol_scaled:\n"
                "        return_window:\n"
                "          - 10\n"
                "          - 20\n"
                "        volatility_window:\n"
                "          - 20\n"
                "        target_volatility:\n"
                "          - 0.2"
            ),
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config["quant"]["parameter_diagnostics"]["enabled"] is True
    assert config["quant"]["parameter_diagnostics"]["max_combinations"] == 4
    assert config["quant"]["parameter_diagnostics"]["grids"]["tsmom_vol_scaled"]["return_window"] == [10, 20]


def test_load_config_accepts_effectiveness_gate_thresholds(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "        target_volatility: 0.2",
            (
                "        target_volatility: 0.2\n"
                "  effectiveness_gates:\n"
                "    min_succeeded_benchmarks: 3\n"
                "    min_benchmark_success_rate_pct: 75.0\n"
                "    max_cost_drag_pct: 1.5\n"
                "    require_parameter_stability: true"
            ),
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config["quant"]["effectiveness_gates"] == {
        "min_succeeded_benchmarks": 3,
        "min_benchmark_success_rate_pct": 75.0,
        "max_cost_drag_pct": 1.5,
        "require_parameter_stability": True,
    }


@pytest.mark.parametrize(
    ("gate_block", "expected"),
    [
        (
            "  effectiveness_gates:\n    unsupported_threshold: 1",
            r"unsupported quant\.effectiveness_gates field",
        ),
        (
            "  effectiveness_gates:\n    min_succeeded_benchmarks: 0",
            r"quant\.effectiveness_gates\.min_succeeded_benchmarks",
        ),
        (
            "  effectiveness_gates:\n    max_cost_drag_pct: -1",
            r"quant\.effectiveness_gates\.max_cost_drag_pct",
        ),
        (
            "  effectiveness_gates:\n    require_walk_forward_stable: \"yes\"",
            r"quant\.effectiveness_gates\.require_walk_forward_stable",
        ),
    ],
)
def test_load_config_rejects_invalid_effectiveness_gate_thresholds(
    tmp_path: Path,
    gate_block: str,
    expected: str,
) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "        target_volatility: 0.2",
            f"        target_volatility: 0.2\n{gate_block}",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=expected):
        load_config(config_path)


def test_load_config_accepts_market_proxy_config(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "  source: binance",
            "  source: binance\n  proxy:\n    enabled: true\n    url: http://proxy.example:8080",
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config["market"]["proxy"] == {
        "enabled": True,
        "url": "http://proxy.example:8080",
    }


@pytest.mark.parametrize(
    ("proxy_block", "expected"),
    [
        ("  proxy: invalid", "market.proxy must be a mapping"),
        ("  proxy:\n    enabled: \"yes\"", "market.proxy.enabled"),
        ("  proxy:\n    enabled: true", "market.proxy.url"),
        ("  proxy:\n    enabled: true\n    url: socks5://proxy.example:1080", "market.proxy.url"),
        (
            "  proxy:\n    enabled: true\n    url: http://user:secret@proxy.example:8080",
            "market.proxy.url must not include credentials",
        ),
    ],
)
def test_load_config_rejects_invalid_market_proxy_config(
    tmp_path: Path, proxy_block: str, expected: str
) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "  source: binance",
            f"  source: binance\n{proxy_block}",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=expected):
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


def test_load_config_accepts_existing_source_based_online_collection_contract(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    _remove_quant_and_ohlcv(config_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        .replace("source: binance", "source: public_market_api")
        .replace("type: rss", "type: public_feed"),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config["market"]["source"] == "public_market_api"
    assert config["text"]["sources"][0]["type"] == "public_feed"


def test_load_config_rejects_unsupported_ohlcv_market_source(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("source: binance", "source: public_market_api"),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="market.source must be one of: binance"):
        load_config(config_path)


def test_load_config_accepts_existing_text_source_type_behavior(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("type: rss", "type: public_feed"),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config["text"]["sources"][0]["type"] == "public_feed"


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ("    storage_dir: data/market/ohlcv", "", "market.ohlcv.storage_dir"),
        ("    storage_dir: data/market/ohlcv", "    storage_dir: runs/ohlcv", "market.ohlcv.storage_dir"),
        ("    timeframes:\n      - 1d\n      - 1h", "    timeframes: []", "market.ohlcv.timeframes"),
        ("      - 1h", "      - 5m", r"market\.ohlcv\.timeframes\[1\]"),
        ("      1h: 720", "", "market.ohlcv.lookback.1h"),
        ("      1h: 720", "      1h: 0", "market.ohlcv.lookback.1h"),
        ("      1h: 720", "      1h: true", "market.ohlcv.lookback.1h"),
    ],
)
def test_load_config_rejects_invalid_ohlcv_config(
    tmp_path: Path, old: str, new: str, expected: str
) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(old, new),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=expected):
        load_config(config_path)


def test_load_config_rejects_absolute_ohlcv_storage_inside_relative_run_output(
    tmp_path: Path,
) -> None:
    config_path = _write_valid_config(tmp_path)
    storage_dir = (tmp_path / "runs" / "ohlcv").resolve().as_posix()
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "    storage_dir: data/market/ohlcv",
            f"    storage_dir: {storage_dir}",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="market.ohlcv.storage_dir"):
        load_config(config_path)


def test_load_config_rejects_quant_enabled_without_ohlcv_config(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            """
  ohlcv:
    storage_dir: data/market/ohlcv
    timeframes:
      - 1d
      - 1h
    lookback:
      1d: 500
      1h: 720
""",
            "\n",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="market.ohlcv must be a mapping when quant.enabled is true"):
        load_config(config_path)


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ("quant:\n  enabled: true", "quant:\n  enabled: \"yes\"", "quant.enabled"),
        (
            "  strategies:\n    - name: tsmom_vol_scaled\n      enabled: true\n      params:\n        return_window: 20\n        volatility_window: 20\n        target_volatility: 0.2",
            "",
            "quant.enabled requires quant.strategies",
        ),
        (
            "  strategies:\n    - name: tsmom_vol_scaled\n      enabled: true\n      params:\n        return_window: 20\n        volatility_window: 20\n        target_volatility: 0.2",
            "  signals:\n    - trend",
            "quant.signals is retired",
        ),
    ],
)
def test_load_config_rejects_invalid_quant_config(
    tmp_path: Path, old: str, new: str, expected: str
) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(old, new),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=expected):
        load_config(config_path)


@pytest.mark.parametrize("signal", ["trend", "momentum", "volatility", "volume_anomaly"])
def test_load_config_rejects_retired_m1_quant_signal_names(tmp_path: Path, signal: str) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            """
  strategies:
    - name: tsmom_vol_scaled
      enabled: true
      params:
        return_window: 20
        volatility_window: 20
        target_volatility: 0.2
""",
            f"""
  signals:
    - {signal}
""",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="quant.signals is retired"):
        load_config(config_path)


@pytest.mark.parametrize(
    ("replacement", "expected"),
    [
        ("  engine: unsupported\n  strategies:\n    - name: tsmom_vol_scaled", "quant.engine"),
        ("  engine: vectorbt\n  strategies: []", "quant.strategies"),
        ("  engine: vectorbt\n  strategies:\n    - name: unsupported", r"quant\.strategies\[0\]\.name"),
        ("  engine: vectorbt\n  strategies:\n    - name: 123", r"quant\.strategies\[0\]\.name"),
        (
            "  engine: vectorbt\n  strategies:\n    - name: tsmom_vol_scaled\n      enabled: \"yes\"",
            r"quant\.strategies\[0\]\.enabled",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: tsmom_vol_scaled\n      params: invalid",
            r"quant\.strategies\[0\]\.params",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: tsmom_vol_scaled\n      params:\n        return_window: 0",
            r"quant\.strategies\[0\]\.params\.return_window must be a positive integer",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: tsmom_vol_scaled\n      params:\n        return_window: \"20\"",
            r"quant\.strategies\[0\]\.params\.return_window must be a positive integer",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: tsmom_vol_scaled\n      params:\n        volatility_window: \"20\"",
            r"quant\.strategies\[0\]\.params\.volatility_window must be a positive integer",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: tsmom_vol_scaled\n      params:\n        target_volatility: 0",
            r"quant\.strategies\[0\]\.params\.target_volatility must be a positive number",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: tsmom_vol_scaled\n      params:\n        target_volatility: \"0.2\"",
            r"quant\.strategies\[0\]\.params\.target_volatility must be a positive number",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: tsmom_vol_scaled\n      backtest: invalid",
            r"quant\.strategies\[0\]\.backtest",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: tsmom_vol_scaled\n      backtest:\n        enabled: \"yes\"",
            r"quant\.strategies\[0\]\.backtest\.enabled",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: tsmom_vol_scaled\n      backtest:\n        initial_cash: 0",
            r"quant\.strategies\[0\]\.backtest\.initial_cash must be a positive number",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: tsmom_vol_scaled\n      backtest:\n        fees_bps: -1",
            r"quant\.strategies\[0\]\.backtest\.fees_bps must be a non-negative number",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: tsmom_vol_scaled\n      backtest:\n        slippage_bps: false",
            r"quant\.strategies\[0\]\.backtest\.slippage_bps must be a non-negative number",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: tsmom_vol_scaled\n      backtest:\n        mode: short",
            r"quant\.strategies\[0\]\.backtest\.mode must be one of: long_flat, long_only",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: breakout_atr_trend\n      params:\n        breakout_window: 0",
            r"quant\.strategies\[0\]\.params\.breakout_window must be a positive integer",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: breakout_atr_trend\n      params:\n        exit_window: \"10\"",
            r"quant\.strategies\[0\]\.params\.exit_window must be a positive integer",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: breakout_atr_trend\n      params:\n        atr_window: false",
            r"quant\.strategies\[0\]\.params\.atr_window must be a positive integer",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: sma_cross_trend\n      params:\n        short_window: 0",
            r"quant\.strategies\[0\]\.params\.short_window must be a positive integer",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: sma_cross_trend\n      params:\n        long_window: false",
            r"quant\.strategies\[0\]\.params\.long_window must be a positive integer",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: sma_cross_trend\n      params:\n        short_window: 50\n        long_window: 20",
            r"quant\.strategies\[0\]\.params\.short_window must be lower than quant\.strategies\[0\]\.params\.long_window",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: bollinger_rsi_reversion\n      params:\n        bollinger_window: 0",
            r"quant\.strategies\[0\]\.params\.bollinger_window must be a positive integer",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: bollinger_rsi_reversion\n      params:\n        band_std: false",
            r"quant\.strategies\[0\]\.params\.band_std must be a positive number",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: bollinger_rsi_reversion\n      params:\n        rsi_window: \"14\"",
            r"quant\.strategies\[0\]\.params\.rsi_window must be a positive integer",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: bollinger_rsi_reversion\n      params:\n        rsi_oversold: 0",
            r"quant\.strategies\[0\]\.params\.rsi_oversold must be a number greater than 0 and lower than 100",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: bollinger_rsi_reversion\n      params:\n        rsi_overbought: 100",
            r"quant\.strategies\[0\]\.params\.rsi_overbought must be a number greater than 0 and lower than 100",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: bollinger_rsi_reversion\n      params:\n        rsi_oversold: 80\n        rsi_overbought: 70",
            (
                r"quant\.strategies\[0\]\.params\.rsi_oversold must be lower than "
                r"quant\.strategies\[0\]\.params\.rsi_overbought"
            ),
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: bollinger_rsi_reversion\n      params:\n        trend_window: false",
            r"quant\.strategies\[0\]\.params\.trend_window must be a positive integer",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: bollinger_rsi_reversion\n      params:\n        trend_filter_pct: 0",
            r"quant\.strategies\[0\]\.params\.trend_filter_pct must be a positive number",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: tsmom_vol_scaled\n  parameter_diagnostics: invalid",
            r"quant\.parameter_diagnostics must be a mapping",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: tsmom_vol_scaled\n  parameter_diagnostics:\n    enabled: \"yes\"",
            r"quant\.parameter_diagnostics\.enabled",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: tsmom_vol_scaled\n  parameter_diagnostics:\n    enabled: true",
            r"quant\.parameter_diagnostics\.max_combinations must be a positive integer",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: tsmom_vol_scaled\n  parameter_diagnostics:\n    enabled: true\n    max_combinations: 0",
            r"quant\.parameter_diagnostics\.max_combinations must be a positive integer",
        ),
        (
            (
                "  engine: vectorbt\n  strategies:\n    - name: tsmom_vol_scaled\n"
                "  parameter_diagnostics:\n    enabled: true\n    max_combinations: 4"
            ),
            r"quant\.parameter_diagnostics\.grids must be a non-empty mapping",
        ),
        (
            (
                "  engine: vectorbt\n  strategies:\n    - name: tsmom_vol_scaled\n"
                "  parameter_diagnostics:\n    enabled: true\n    max_combinations: 4\n"
                "    grids:\n      unsupported:\n        return_window:\n          - 10"
            ),
            r"quant\.parameter_diagnostics\.grids\.unsupported must be one of:",
        ),
        (
            (
                "  engine: vectorbt\n  strategies:\n    - name: tsmom_vol_scaled\n"
                "  parameter_diagnostics:\n    enabled: true\n    max_combinations: 4\n"
                "    grids:\n      tsmom_vol_scaled:\n        breakout_window:\n          - 10"
            ),
            r"quant\.parameter_diagnostics\.grids\.tsmom_vol_scaled\.breakout_window is not supported",
        ),
        (
            (
                "  engine: vectorbt\n  strategies:\n    - name: tsmom_vol_scaled\n"
                "  parameter_diagnostics:\n    enabled: true\n    max_combinations: 4\n"
                "    grids:\n      tsmom_vol_scaled:\n        return_window: 10"
            ),
            r"quant\.parameter_diagnostics\.grids\.tsmom_vol_scaled\.return_window must be a non-empty list",
        ),
        (
            (
                "  engine: vectorbt\n  strategies:\n    - name: tsmom_vol_scaled\n"
                "  parameter_diagnostics:\n    enabled: true\n    max_combinations: 4\n"
                "    grids:\n      tsmom_vol_scaled:\n        return_window:\n          - \"10\""
            ),
            r"quant\.parameter_diagnostics\.grids\.tsmom_vol_scaled\.return_window\[0\] must be a positive integer",
        ),
        (
            (
                "  engine: vectorbt\n  strategies:\n    - name: tsmom_vol_scaled\n"
                "  parameter_diagnostics:\n    enabled: true\n    max_combinations: 2\n"
                "    grids:\n      tsmom_vol_scaled:\n        return_window:\n          - 10\n          - 20\n"
                "        volatility_window:\n          - 10\n          - 20"
            ),
            r"quant\.parameter_diagnostics\.grids\.tsmom_vol_scaled has 4 combinations; max_combinations is 2",
        ),
    ],
)
def test_load_config_rejects_invalid_quant_strategy_config(
    tmp_path: Path,
    replacement: str,
    expected: str,
) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            """
  strategies:
    - name: tsmom_vol_scaled
      enabled: true
      params:
        return_window: 20
        volatility_window: 20
        target_volatility: 0.2
""",
            f"\n{replacement}\n",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=expected):
        load_config(config_path)


def test_load_config_rejects_quant_enabled_when_market_disabled(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("market:\n  enabled: true", "market:\n  enabled: false"),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="quant.enabled requires market.enabled"):
        load_config(config_path)


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
  ohlcv:
    storage_dir: data/market/ohlcv
    timeframes:
      - 1d
      - 1h
    lookback:
      1d: 500
      1h: 720
quant:
  enabled: true
  engine: vectorbt
  strategies:
    - name: tsmom_vol_scaled
      enabled: true
      params:
        return_window: 20
        volatility_window: 20
        target_volatility: 0.2
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


def _remove_quant_and_ohlcv(config_path: Path) -> None:
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            """
  ohlcv:
    storage_dir: data/market/ohlcv
    timeframes:
      - 1d
      - 1h
    lookback:
      1d: 500
      1h: 720
quant:
  enabled: true
  engine: vectorbt
  strategies:
    - name: tsmom_vol_scaled
      enabled: true
      params:
        return_window: 20
        volatility_window: 20
        target_volatility: 0.2
""",
            "\n",
        ),
        encoding="utf-8",
    )
