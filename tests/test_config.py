from pathlib import Path

import pytest

from halpha.config import ConfigError, load_config


_DERIVATIVES_CONFIG_BLOCK = """  derivatives:
    enabled: true
    source: binance_usdm
    symbols:
      - BTCUSDT
    data_classes:
      - funding_rate
      - open_interest
      - premium_index
    periods:
      - 1h
      - 4h
      - 1d
    lookback:
      1h: 720
      4h: 180
      1d: 90
"""


def test_config_example_loads_successfully() -> None:
    config = load_config(Path("config.example.yaml"))

    assert config["run"]["output_dir"] == "runs"
    assert config["logging"] == {"output_dir": "logs"}
    assert config["market"]["source"] == "binance_usdm"
    assert config["market"]["proxy"] == {"enabled": False}
    assert config["market"]["symbols"] == ["BTCUSDT"]
    assert config["market"]["ohlcv"]["storage_dir"] == "data/market/ohlcv"
    assert config["market"]["ohlcv"]["sources"] == [
        "binance_usdm",
        "binance",
        "binance_spot",
        "okx_spot",
        "okx_swap",
        "bybit_spot",
        "bybit_swap",
        "kucoin_spot",
        "kucoin_swap",
        "bitget_spot",
        "bitget_swap",
        "kraken_spot",
        "coinbase_spot",
    ]
    assert config["market"]["ohlcv"]["timeframes"] == [
        "1m",
        "5m",
        "15m",
        "1h",
        "4h",
        "1d",
        "1w",
        "1M",
    ]
    assert config["market"]["ohlcv"]["lookback"] == {
        "1m": 1440,
        "5m": 2016,
        "15m": 2016,
        "1h": 720,
        "4h": 720,
        "1d": 500,
        "1w": 260,
        "1M": 120,
    }
    assert config["market"]["derivatives"] == {
        "enabled": True,
        "source": "binance_usdm",
        "symbols": ["BTCUSDT"],
        "data_classes": [
            "funding_rate",
            "open_interest",
            "premium_index",
            "basis",
            "spread_depth",
            "liquidation_summary",
        ],
        "periods": ["1h", "4h", "1d"],
        "lookback": {"1h": 720, "4h": 180, "1d": 90},
    }
    assert config["market"]["anomalies"] == {"enabled": False}
    assert config["macro_calendar"] == {"enabled": False}
    assert config["onchain_flow"] == {"enabled": False}
    assert config["user_state"] == {"enabled": False, "path": "user_state.local.yaml"}
    assert config["dashboard"] == {
        "display_timezone": "Asia/Shanghai",
        "pnl_color_scheme": "green_profit_red_loss",
        "timestamp_hour_cycle": "24h",
        "timestamp_date_order": "year_first",
    }
    assert config["monitor"] == {
        "enabled": False,
        "interval_seconds": 300,
        "failure_backoff_max_seconds": 3600,
        "output_dir": "runs/monitor",
    }
    assert config["quant"]["enabled"] is True
    assert config["quant"]["engine"] == "vectorbt"
    assert [strategy["name"] for strategy in config["quant"]["strategies"]] == [
        "tsmom_vol_scaled",
        "signed_tsmom_trend",
        "breakout_atr_trend",
        "sma_cross_trend",
        "sma_cross_long_short",
        "bollinger_rsi_reversion",
        "bollinger_rsi_long_short",
    ]
    assert all(strategy["enabled"] is True for strategy in config["quant"]["strategies"])
    assert all(strategy["backtest"]["enabled"] is True for strategy in config["quant"]["strategies"])
    assert config["quant"]["strategies"][0]["params"] == {
        "return_window": 120,
        "volatility_window": 60,
        "target_volatility": 0.2,
    }
    assert config["quant"]["strategies"][1]["params"] == {
        "return_window": 120,
        "deadband_pct": 1.0,
    }
    assert config["quant"]["strategies"][2]["params"] == {
        "breakout_window": 120,
        "exit_window": 20,
        "atr_window": 14,
    }
    assert config["quant"]["strategies"][3]["params"] == {
        "short_window": 20,
        "long_window": 30,
    }
    assert config["quant"]["strategies"][4]["params"] == {
        "short_window": 20,
        "long_window": 30,
        "neutral_band_pct": 0.5,
    }
    assert config["quant"]["strategies"][5]["params"] == {
        "bollinger_window": 20,
        "band_std": 2.0,
        "rsi_window": 14,
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "trend_window": 100,
        "trend_filter_pct": 10.0,
    }
    assert config["quant"]["strategies"][6]["params"] == {
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
        "bollinger_rsi_long_short",
        "bollinger_rsi_reversion",
        "breakout_atr_trend",
        "signed_tsmom_trend",
        "sma_cross_long_short",
        "sma_cross_trend",
        "tsmom_vol_scaled",
    ]
    assert config["text"]["intelligence"]["enabled"] is True
    assert config["text"]["intelligence"]["model_cache_dir"] == "data/models/text"
    assert config["text"]["intelligence"]["allow_model_download"] is False
    assert config["text"]["intelligence"]["models"]["embedding"] == {
        "provider": "sentence_transformers",
        "name": "sentence-transformers/all-MiniLM-L6-v2",
        "revision": "pinned",
    }
    assert config["text"]["intelligence"]["thresholds"]["duplicate_similarity"] == 0.92
    assert config["text"]["sources"][0]["type"] == "rss"
    assert config["report"]["language"] == "zh-CN"


def test_load_config_accepts_targeted_strategy_params(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "      params:\n        return_window: 20\n        volatility_window: 20\n        target_volatility: 0.2",
            (
                "      params:\n        return_window: 20\n        volatility_window: 20\n        target_volatility: 0.2\n"
                "      targeted_params:\n"
                "        - source: binance_usdm\n"
                "          symbol: BTCUSDT\n"
                "          timeframe: 4h\n"
                "          params:\n"
                "            return_window: 80\n"
                "            volatility_window: 40"
            ),
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    profile = config["quant"]["strategies"][0]["targeted_params"][0]
    assert profile == {
        "source": "binance_usdm",
        "symbol": "BTCUSDT",
        "timeframe": "4h",
        "params": {"return_window": 80, "volatility_window": 40},
    }


@pytest.mark.parametrize(
    ("targeted_block", "expected"),
    [
        ("targeted_params: invalid", r"targeted_params must be a list"),
        (
            "targeted_params:\n"
            "        - source: binance\n"
            "          symbol: BTCUSDT\n"
            "          timeframe: 1d\n"
            "          params: invalid",
            r"targeted_params\[0\]\.params must be a mapping",
        ),
        (
            "targeted_params:\n"
            "        - source: binance\n"
            "          symbol: BTCUSDT\n"
            "          timeframe: 1d\n"
            "          params:\n"
            "            return_window: 0",
            r"targeted_params\[0\]\.params\.return_window",
        ),
        (
            "targeted_params:\n"
            "        - source: binance\n"
            "          symbol: BTCUSDT\n"
            "          timeframe: 1d\n"
            "          params:\n"
            "            return_window: 20\n"
            "        - source: binance\n"
            "          symbol: BTCUSDT\n"
            "          timeframe: 1d\n"
            "          params:\n"
            "            return_window: 30",
            r"duplicates targeted params",
        ),
    ],
)
def test_load_config_rejects_invalid_targeted_strategy_params(
    tmp_path: Path,
    targeted_block: str,
    expected: str,
) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "      params:\n        return_window: 20\n        volatility_window: 20\n        target_volatility: 0.2",
            (
                "      params:\n        return_window: 20\n        volatility_window: 20\n"
                f"        target_volatility: 0.2\n      {targeted_block}"
            ),
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=expected):
        load_config(config_path)


def test_load_config_rejects_non_mapping_root(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("- run\n- market\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="config root must be a mapping"):
        load_config(config_path)


@pytest.mark.parametrize("section", ["run", "logging", "market", "monitor", "quant", "text", "report", "codex"])
def test_load_config_rejects_non_mapping_sections(tmp_path: Path, section: str) -> None:
    config_path = _write_valid_config(tmp_path)
    section_blocks = {
        "run": "run:\n  output_dir: runs",
        "logging": "logging:\n  output_dir: logs",
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
        "monitor": "monitor:\n  enabled: false",
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


def test_load_config_accepts_live_collection_config(tmp_path: Path) -> None:
    config_path = _write_config_text(
        tmp_path,
        """
run:
  output_dir: runs
market:
  enabled: false
text:
  enabled: false
report:
  language: zh-CN
codex:
  enabled: false
live:
  enabled: true
  tick_seconds: 15
  collections:
    text_event:
      enabled: true
      cadence_seconds: 300
      lookback_seconds: 3600
    macro_calendar:
      enabled: true
      cadence_seconds: 3600
      lookback_seconds: 86400
      lookahead_seconds: 604800
  reports:
    daily:
      enabled: false
    triggers:
      data_quality_degraded:
        enabled: true
        cooldown_seconds: 3600
""",
    )

    config = load_config(config_path)

    assert config["live"]["enabled"] is True


def test_load_config_rejects_unknown_live_collection_type(tmp_path: Path) -> None:
    config_path = _write_config_text(
        tmp_path,
        """
run:
  output_dir: runs
market:
  enabled: false
text:
  enabled: false
report:
  language: zh-CN
codex:
  enabled: false
live:
  enabled: true
  collections:
    unsupported:
      enabled: true
      cadence_seconds: 300
      lookback_seconds: 3600
""",
    )

    with pytest.raises(ConfigError, match="unsupported live.collections data type"):
        load_config(config_path)


def test_load_config_rejects_enabled_live_collection_without_lookback(tmp_path: Path) -> None:
    config_path = _write_config_text(
        tmp_path,
        """
run:
  output_dir: runs
market:
  enabled: false
text:
  enabled: false
report:
  language: zh-CN
codex:
  enabled: false
live:
  enabled: true
  collections:
    text_event:
      enabled: true
      cadence_seconds: 300
""",
    )

    with pytest.raises(ConfigError, match=r"live\.collections\.text_event\.lookback_seconds must be a positive integer"):
        load_config(config_path)


def test_load_config_accepts_enabled_user_state_config(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    _add_user_state_config(config_path)

    config = load_config(config_path)

    assert config["user_state"] == {"enabled": True, "path": "user_state.local.yaml"}


def test_load_config_accepts_dashboard_display_preferences(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "quant:\n",
            (
                "dashboard:\n"
                "  display_timezone: UTC\n"
                "  pnl_color_scheme: red_profit_green_loss\n\n"
                "quant:\n"
            ),
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config["dashboard"] == {
        "display_timezone": "UTC",
        "pnl_color_scheme": "red_profit_green_loss",
    }


def test_load_config_rejects_invalid_run_timezone(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "  output_dir: runs",
            "  output_dir: runs\n  timezone: Invalid/Zone",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="run.timezone is not an available IANA timezone"):
        load_config(config_path)


def test_load_config_accepts_logging_output_dir(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)

    config = load_config(config_path)

    assert config["logging"] == {"output_dir": "logs"}


@pytest.mark.parametrize(
    ("block", "expected"),
    [
        ("dashboard: invalid", "dashboard must be a mapping"),
        ("dashboard:\n  display_timezone: ''", "dashboard.display_timezone"),
        (
            "dashboard:\n  display_timezone: Invalid/Zone",
            "dashboard.display_timezone is not an available IANA timezone",
        ),
        (
            "dashboard:\n  pnl_color_scheme: purple_profit_orange_loss",
            "dashboard.pnl_color_scheme must be one of",
        ),
        ("dashboard:\n  unsupported: true", "unsupported dashboard field"),
    ],
)
def test_load_config_rejects_invalid_dashboard_config(
    tmp_path: Path,
    block: str,
    expected: str,
) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("quant:\n", f"{block}\n\nquant:\n"),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=expected):
        load_config(config_path)


@pytest.mark.parametrize(
    ("block", "expected"),
    [
        ("logging: invalid", "logging must be a mapping"),
        ("logging:\n  output_dir: ''", "logging.output_dir"),
        ("logging:\n  unsupported: true", "unsupported logging field"),
    ],
)
def test_load_config_rejects_invalid_logging_config(
    tmp_path: Path,
    block: str,
    expected: str,
) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("logging:\n  output_dir: logs", block),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=expected):
        load_config(config_path)


@pytest.mark.parametrize(
    ("block", "expected"),
    [
        ("user_state: invalid", "user_state must be a mapping"),
        ("user_state:\n  enabled: \"yes\"", "user_state.enabled"),
        ("user_state:\n  enabled: true", "user_state.path"),
        ("user_state:\n  enabled: false\n  unsupported: true", "unsupported user_state field"),
    ],
)
def test_load_config_rejects_invalid_user_state_config(
    tmp_path: Path,
    block: str,
    expected: str,
) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("quant:\n", f"{block}\n\nquant:\n"),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=expected):
        load_config(config_path)


@pytest.mark.parametrize(
    ("monitor_block", "expected"),
    [
        ("  enabled: \"yes\"", r"monitor\.enabled must be a boolean"),
        ("  interval_seconds: 0", r"monitor\.interval_seconds must be a positive integer"),
        ("  failure_backoff_max_seconds: 0", r"monitor\.failure_backoff_max_seconds must be a positive integer"),
        ("  max_cycles: false", r"monitor\.max_cycles must be a positive integer"),
        ("  cooldown_seconds: -1", r"monitor\.cooldown_seconds must be a positive integer"),
        ("  output_dir: ''", r"monitor\.output_dir must be a non-empty string"),
        ("  target_stage: ''", r"monitor\.target_stage must be a non-empty string"),
        ("  no_codex: \"no\"", r"monitor\.no_codex must be a boolean"),
        ("  source_cadence_seconds: []", r"monitor\.source_cadence_seconds must be a non-empty mapping"),
        ("  source_cadence_seconds:\n    text: 0", r"monitor\.source_cadence_seconds\.text must be a positive integer"),
        (
            "  source_cadence_seconds:\n    private_feed: 60",
            r"unsupported monitor\.source_cadence_seconds source\(s\): private_feed",
        ),
        ("  surprise: value", r"unsupported monitor field\(s\): surprise"),
    ],
)
def test_load_config_rejects_invalid_monitor_config(
    tmp_path: Path,
    monitor_block: str,
    expected: str,
) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "monitor:\n  enabled: false",
            f"monitor:\n{monitor_block}",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=expected):
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


def test_load_config_accepts_pair_zscore_reversion_strategy_config(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "    - name: tsmom_vol_scaled",
            (
                "    - name: pair_zscore_reversion\n"
                "      params:\n"
                "        lookback_window: 20\n"
                "        entry_zscore: 2.0\n"
                "        exit_zscore: 0.5\n"
                "        hedge_ratio: 1.0\n"
                "    - name: tsmom_vol_scaled"
            ),
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config["quant"]["strategies"][0]["name"] == "pair_zscore_reversion"
    assert config["quant"]["strategies"][0]["params"]["hedge_ratio"] == 1.0


def test_load_config_accepts_cross_sectional_momentum_strategy_config(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "    - name: tsmom_vol_scaled",
            (
                "    - name: cross_sectional_momentum\n"
                "      params:\n"
                "        lookback_window: 20\n"
                "        long_count: 1\n"
                "        short_count: 1\n"
                "        min_instrument_count: 3\n"
                "    - name: tsmom_vol_scaled"
            ),
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config["quant"]["strategies"][0]["name"] == "cross_sectional_momentum"
    assert config["quant"]["strategies"][0]["params"]["min_instrument_count"] == 3


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
                "    max_turnover: 12.0\n"
                "    max_abs_funding_drag_pct: 2.0\n"
                "    max_average_gross_exposure_pct: 150.0\n"
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
        "max_turnover": 12.0,
        "max_abs_funding_drag_pct": 2.0,
        "max_average_gross_exposure_pct": 150.0,
        "require_parameter_stability": True,
    }


def test_load_config_accepts_quant_walk_forward_policy(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "        target_volatility: 0.2",
            (
                "        target_volatility: 0.2\n"
                "  walk_forward_policy:\n"
                "    calibration_rows: 120\n"
                "    window_rows: 180\n"
                "    min_window_rows: 120\n"
                "    min_windows: 3"
            ),
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config["quant"]["walk_forward_policy"] == {
        "calibration_rows": 120,
        "window_rows": 180,
        "min_window_rows": 120,
        "min_windows": 3,
    }


def test_load_config_accepts_lifecycle_policy_records(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "        target_volatility: 0.2",
            (
                "        target_volatility: 0.2\n"
                "  lifecycle_policy:\n"
                "    records:\n"
                "      - action: retire\n"
                "        strategy_name: tsmom_vol_scaled\n"
                "        reason: review decision\n"
                "        created_at: 2026-06-06T00:00:00Z\n"
                "        scope:\n"
                "          symbol: BTCUSDT\n"
                "          timeframe: 1d"
            ),
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    record = config["quant"]["lifecycle_policy"]["records"][0]
    assert record["action"] == "retire"
    assert record["strategy_name"] == "tsmom_vol_scaled"
    assert record["scope"] == {"symbol": "BTCUSDT", "timeframe": "1d"}


@pytest.mark.parametrize(
    ("policy_block", "expected"),
    [
        ("  lifecycle_policy:\n    unsupported: true", r"unsupported quant\.lifecycle_policy field"),
        ("  lifecycle_policy:\n    records: invalid", r"quant\.lifecycle_policy\.records must be a list"),
        (
            "  lifecycle_policy:\n    records:\n      - action: freeze\n        strategy_name: tsmom_vol_scaled\n        reason: review",
            r"quant\.lifecycle_policy\.records\[0\]\.action must be one of:",
        ),
        (
            "  lifecycle_policy:\n    records:\n      - action: retire\n        strategy_name: unknown\n        reason: review",
            r"quant\.lifecycle_policy\.records\[0\]\.strategy_name must be one of:",
        ),
        (
            "  lifecycle_policy:\n    records:\n      - action: retire\n        strategy_name: tsmom_vol_scaled\n        reason: review\n        scope:\n          private_path: secret",
            r"unsupported quant\.lifecycle_policy\.records\[0\]\.scope field",
        ),
    ],
)
def test_load_config_rejects_invalid_lifecycle_policy_records(
    tmp_path: Path,
    policy_block: str,
    expected: str,
) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "        target_volatility: 0.2",
            f"        target_volatility: 0.2\n{policy_block}",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=expected):
        load_config(config_path)


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


@pytest.mark.parametrize(
    ("policy_block", "expected"),
    [
        (
            "  walk_forward_policy:\n    unsupported: 1",
            r"unsupported quant\.walk_forward_policy field",
        ),
        (
            "  walk_forward_policy:\n    calibration_rows: -1",
            r"quant\.walk_forward_policy\.calibration_rows",
        ),
        (
            "  walk_forward_policy:\n    window_rows: 0",
            r"quant\.walk_forward_policy\.window_rows",
        ),
        (
            "  walk_forward_policy:\n    window_rows: 20\n    min_window_rows: 21",
            r"quant\.walk_forward_policy\.min_window_rows",
        ),
    ],
)
def test_load_config_rejects_invalid_quant_walk_forward_policy(
    tmp_path: Path,
    policy_block: str,
    expected: str,
) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "        target_volatility: 0.2",
            f"        target_volatility: 0.2\n{policy_block}",
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


def test_load_config_accepts_omitted_derivatives_config(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)

    config = load_config(config_path)

    assert "derivatives" not in config["market"]


def test_load_config_accepts_enabled_derivatives_config(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    _add_derivatives_config(config_path)

    config = load_config(config_path)

    assert config["market"]["derivatives"]["source"] == "binance_usdm"
    assert config["market"]["derivatives"]["symbols"] == ["BTCUSDT"]
    assert config["market"]["derivatives"]["data_classes"] == [
        "funding_rate",
        "open_interest",
        "premium_index",
    ]
    assert config["market"]["derivatives"]["periods"] == ["1h", "4h", "1d"]
    assert config["market"]["derivatives"]["lookback"] == {"1h": 720, "4h": 180, "1d": 90}


def test_load_config_accepts_enabled_macro_calendar_config(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    _add_macro_calendar_config(config_path)

    config = load_config(config_path)

    assert config["macro_calendar"] == {
        "enabled": True,
        "source": "federal_reserve_fomc",
        "data_classes": ["central_bank_event"],
        "regions": ["US"],
        "lookback_days": 7,
        "lookahead_days": 45,
    }


def test_load_config_accepts_enabled_onchain_flow_config(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    _add_onchain_flow_config(config_path)

    config = load_config(config_path)

    assert config["onchain_flow"] == {
        "enabled": True,
        "source": "public_aggregate",
        "data_classes": [
            "stablecoin_supply",
            "chain_activity",
            "network_congestion",
            "exchange_flow_availability",
        ],
        "assets": ["ALL_STABLECOINS", "BTC"],
        "chains": ["all", "bitcoin"],
        "lookback_days": 7,
    }


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ("macro_calendar:\n  enabled: true", "macro_calendar:\n  enabled: \"yes\"", "macro_calendar.enabled"),
        ("  source: federal_reserve_fomc", "  source: unsupported", "macro_calendar.source"),
        ("  data_classes:\n    - central_bank_event", "  data_classes: []", "macro_calendar.data_classes"),
        ("    - central_bank_event", "    - unsupported", r"macro_calendar\.data_classes\[0\]"),
        ("  regions:\n    - US", "  regions: []", "macro_calendar.regions"),
        ("    - US", "    - EU", r"macro_calendar\.regions\[0\]"),
        ("  lookback_days: 7", "  lookback_days: 0", "macro_calendar.lookback_days"),
        ("  lookahead_days: 45", "  lookahead_days: true", "macro_calendar.lookahead_days"),
        ("  source: federal_reserve_fomc", "  source: federal_reserve_fomc\n  unsupported: true", "unsupported macro_calendar field"),
        (
            "  source: federal_reserve_fomc",
            "  source: federal_reserve_fomc\n  source_url: file:///tmp/calendar.html",
            "macro_calendar.source_url",
        ),
        (
            "  source: federal_reserve_fomc",
            "  source: federal_reserve_fomc\n  source_url: http://user:secret@example.com/calendar",
            "macro_calendar.source_url must not include credentials",
        ),
    ],
)
def test_load_config_rejects_invalid_macro_calendar_config(
    tmp_path: Path,
    old: str,
    new: str,
    expected: str,
) -> None:
    config_path = _write_valid_config(tmp_path)
    _add_macro_calendar_config(config_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(old, new, 1),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=expected):
        load_config(config_path)


def test_load_config_rejects_non_mapping_macro_calendar_config(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "quant:\n",
            "macro_calendar: invalid\n\nquant:\n",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="macro_calendar must be a mapping"):
        load_config(config_path)


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ("onchain_flow:\n  enabled: true", "onchain_flow:\n  enabled: \"yes\"", "onchain_flow.enabled"),
        ("  source: public_aggregate", "  source: unsupported", "onchain_flow.source"),
        (
            "  data_classes:\n    - stablecoin_supply\n    - chain_activity\n    - network_congestion\n    - exchange_flow_availability",
            "  data_classes: []",
            "onchain_flow.data_classes",
        ),
        ("    - stablecoin_supply", "    - unsupported", r"onchain_flow\.data_classes\[0\]"),
        ("  assets:\n    - ALL_STABLECOINS\n    - BTC", "  assets: []", "onchain_flow.assets"),
        ("    - ALL_STABLECOINS", "    - DOGE", r"onchain_flow\.assets\[0\]"),
        ("  chains:\n    - all\n    - bitcoin", "  chains: []", "onchain_flow.chains"),
        ("    - all", "    - ethereum", r"onchain_flow\.chains\[0\]"),
        ("  lookback_days: 7", "  lookback_days: 0", "onchain_flow.lookback_days"),
        ("  source: public_aggregate", "  source: public_aggregate\n  unsupported: true", "unsupported onchain_flow field"),
        (
            "  source: public_aggregate",
            "  source: public_aggregate\n  stablecoin_source_url: file:///tmp/stablecoins.json",
            "onchain_flow.stablecoin_source_url",
        ),
        (
            "  source: public_aggregate",
            "  source: public_aggregate\n  chain_activity_source_url: http://user:secret@example.com/chart",
            "onchain_flow.chain_activity_source_url must not include credentials",
        ),
        (
            "  source: public_aggregate",
            "  source: public_aggregate\n  network_congestion_source_url: socks5://proxy.example/chart",
            "onchain_flow.network_congestion_source_url",
        ),
    ],
)
def test_load_config_rejects_invalid_onchain_flow_config(
    tmp_path: Path,
    old: str,
    new: str,
    expected: str,
) -> None:
    config_path = _write_valid_config(tmp_path)
    _add_onchain_flow_config(config_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(old, new, 1),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=expected):
        load_config(config_path)


def test_load_config_rejects_non_mapping_onchain_flow_config(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "quant:\n",
            "onchain_flow: invalid\n\nquant:\n",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="onchain_flow must be a mapping"):
        load_config(config_path)


def test_load_config_rejects_enabled_derivatives_when_market_disabled(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    _add_derivatives_config(config_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("market:\n  enabled: true", "market:\n  enabled: false"),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="market.derivatives.enabled requires market.enabled"):
        load_config(config_path)


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        (_DERIVATIVES_CONFIG_BLOCK, "  derivatives: invalid\n", "market.derivatives must be a mapping"),
        ("    enabled: true", "    enabled: \"yes\"", "market.derivatives.enabled"),
        (
            "    source: binance_usdm",
            "    source: unsupported",
            "market.derivatives.source must be one of: binance_usdm",
        ),
        ("    source: binance_usdm\n", "", "market.derivatives.source"),
        (
            "    symbols:\n      - BTCUSDT\n",
            "",
            "market.derivatives.symbols",
        ),
        (
            "    symbols:\n      - BTCUSDT",
            "    symbols: []",
            "market.derivatives.symbols",
        ),
        (
            "    data_classes:\n      - funding_rate\n      - open_interest\n      - premium_index\n",
            "",
            "market.derivatives.data_classes",
        ),
        (
            "      - premium_index",
            "      - unsupported",
            r"market\.derivatives\.data_classes\[2\]",
        ),
        ("      - 4h", "      - 3h", r"market\.derivatives\.periods\[1\]"),
        ("    lookback:\n      1h: 720\n      4h: 180\n      1d: 90\n", "", "market.derivatives.lookback"),
        ("      4h: 180\n", "", "market.derivatives.lookback.4h"),
        ("      4h: 180", "      4h: 0", "market.derivatives.lookback.4h"),
        ("      1d: 90", "      1d: 90\n      12h: 30", "unsupported market.derivatives.lookback period"),
        ("    periods:", "    unsupported_field: true\n    periods:", "unsupported market.derivatives field"),
    ],
)
def test_load_config_rejects_invalid_derivatives_config(
    tmp_path: Path, old: str, new: str, expected: str
) -> None:
    config_path = _write_valid_config(tmp_path)
    _add_derivatives_config(config_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(old, new),
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

    with pytest.raises(ConfigError, match="market.source must be one of: binance, binance_spot, binance_usdm"):
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
        ("      - 1h", "      - 2m", r"market\.ohlcv\.timeframes\[1\]"),
        ("    storage_dir: data/market/ohlcv", "    storage_dir: data/market/ohlcv\n    sources:\n      - unsupported_exchange", r"market\.ohlcv\.sources\[0\]"),
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


def test_load_config_rejects_absolute_ohlcv_storage_inside_runtime_run_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
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


def test_load_config_rejects_absolute_ohlcv_storage_inside_runtime_run_output_for_external_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    config_dir = tmp_path / "external-config"
    runtime_root.mkdir()
    config_dir.mkdir()
    monkeypatch.chdir(runtime_root)
    config_path = _write_valid_config(config_dir)
    storage_dir = (runtime_root / "runs" / "ohlcv").resolve().as_posix()
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
            "  engine: vectorbt\n  strategies:\n    - name: signed_tsmom_trend\n      params:\n        return_window: 0",
            r"quant\.strategies\[0\]\.params\.return_window must be a positive integer",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: signed_tsmom_trend\n      params:\n        deadband_pct: -1",
            r"quant\.strategies\[0\]\.params\.deadband_pct must be a number between 0.0 and 100.0",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: signed_tsmom_trend\n      params:\n        volatility_filter_enabled: \"yes\"",
            r"quant\.strategies\[0\]\.params\.volatility_filter_enabled must be a boolean",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: signed_tsmom_trend\n      params:\n        volatility_filter_window: 0",
            r"quant\.strategies\[0\]\.params\.volatility_filter_window must be a positive integer",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: signed_tsmom_trend\n      params:\n        max_realized_volatility_pct: 0",
            r"quant\.strategies\[0\]\.params\.max_realized_volatility_pct must be a positive number",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: signed_tsmom_trend\n      params:\n        funding_rate_filter_enabled: \"yes\"",
            r"quant\.strategies\[0\]\.params\.funding_rate_filter_enabled must be a boolean",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: signed_tsmom_trend\n      params:\n        max_abs_funding_rate: 0",
            r"quant\.strategies\[0\]\.params\.max_abs_funding_rate must be a positive number",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: signed_tsmom_trend\n      params:\n        market_anomaly_filter_enabled: \"yes\"",
            r"quant\.strategies\[0\]\.params\.market_anomaly_filter_enabled must be a boolean",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: signed_tsmom_trend\n      params:\n        market_anomaly_filter_lookback_hours: 0",
            r"quant\.strategies\[0\]\.params\.market_anomaly_filter_lookback_hours must be a positive number",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: signed_tsmom_trend\n      params:\n        market_anomaly_filter_min_count: 0",
            r"quant\.strategies\[0\]\.params\.market_anomaly_filter_min_count must be a positive integer",
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
            "  engine: vectorbt\n  strategies:\n    - name: sma_cross_long_short\n      params:\n        short_window: 0",
            r"quant\.strategies\[0\]\.params\.short_window must be a positive integer",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: sma_cross_long_short\n      params:\n        short_window: 50\n        long_window: 20",
            r"quant\.strategies\[0\]\.params\.short_window must be lower than quant\.strategies\[0\]\.params\.long_window",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: sma_cross_long_short\n      params:\n        neutral_band_pct: -1",
            r"quant\.strategies\[0\]\.params\.neutral_band_pct must be a number between 0.0 and 100.0",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: pair_zscore_reversion\n      params:\n        lookback_window: 0",
            r"quant\.strategies\[0\]\.params\.lookback_window must be a positive integer",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: pair_zscore_reversion\n      params:\n        entry_zscore: 0",
            r"quant\.strategies\[0\]\.params\.entry_zscore must be a positive number",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: pair_zscore_reversion\n      params:\n        exit_zscore: -1",
            r"quant\.strategies\[0\]\.params\.exit_zscore must be a non-negative number",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: pair_zscore_reversion\n      params:\n        entry_zscore: 1.0\n        exit_zscore: 1.0",
            r"quant\.strategies\[0\]\.params\.exit_zscore must be lower than quant\.strategies\[0\]\.params\.entry_zscore",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: pair_zscore_reversion\n      params:\n        hedge_ratio: 0",
            r"quant\.strategies\[0\]\.params\.hedge_ratio must be a positive number",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: cross_sectional_momentum\n      params:\n        lookback_window: 0",
            r"quant\.strategies\[0\]\.params\.lookback_window must be a positive integer",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: cross_sectional_momentum\n      params:\n        long_count: 0",
            r"quant\.strategies\[0\]\.params\.long_count must be a positive integer",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: cross_sectional_momentum\n      params:\n        short_count: false",
            r"quant\.strategies\[0\]\.params\.short_count must be a positive integer",
        ),
        (
            (
                "  engine: vectorbt\n  strategies:\n    - name: cross_sectional_momentum\n"
                "      params:\n        long_count: 2\n        short_count: 2\n        min_instrument_count: 3"
            ),
            (
                r"quant\.strategies\[0\]\.params\.min_instrument_count must be at least "
                r"quant\.strategies\[0\]\.params\.long_count \+ quant\.strategies\[0\]\.params\.short_count"
            ),
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
            "  engine: vectorbt\n  strategies:\n    - name: bollinger_rsi_long_short\n      params:\n        bollinger_window: 0",
            r"quant\.strategies\[0\]\.params\.bollinger_window must be a positive integer",
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: bollinger_rsi_long_short\n      params:\n        rsi_oversold: 80\n        rsi_overbought: 70",
            (
                r"quant\.strategies\[0\]\.params\.rsi_oversold must be lower than "
                r"quant\.strategies\[0\]\.params\.rsi_overbought"
            ),
        ),
        (
            "  engine: vectorbt\n  strategies:\n    - name: bollinger_rsi_long_short\n      params:\n        trend_filter_pct: 0",
            r"quant\.strategies\[0\]\.params\.trend_filter_pct must be a positive number",
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


def test_load_config_accepts_text_intelligence_config(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    _add_text_intelligence_config(config_path)

    config = load_config(config_path)

    intelligence = config["text"]["intelligence"]
    assert intelligence["allow_model_download"] is False
    assert sorted(intelligence["models"]) == ["classifier", "embedding", "ner", "sentiment"]
    assert intelligence["models"]["classifier"]["provider"] == "transformers_zero_shot"
    assert intelligence["thresholds"]["max_topic_window_hours"] == 48


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        (
            "    allow_model_download: false",
            "    allow_model_download: false\n    unsupported: true",
            r"unsupported text\.intelligence field",
        ),
        (
            "      ner:\n        provider: gliner",
            "      unsupported:\n        provider: gliner",
            r"unsupported text\.intelligence\.models role",
        ),
        (
            "        provider: sentence_transformers",
            "        provider: transformers",
            r"text\.intelligence\.models\.embedding\.provider",
        ),
        (
            "        revision: pinned",
            "",
            r"text\.intelligence\.models\.embedding\.revision",
        ),
        (
            "      duplicate_similarity: 0.92",
            "      duplicate_similarity: 1.5",
            r"text\.intelligence\.thresholds\.duplicate_similarity",
        ),
        (
            "      max_topic_window_hours: 48",
            "      max_topic_window_hours: 0",
            r"text\.intelligence\.thresholds\.max_topic_window_hours",
        ),
        (
            "      entity_accept_score: 0.50",
            "",
            r"text\.intelligence\.thresholds missing required field",
        ),
    ],
)
def test_load_config_rejects_invalid_text_intelligence_config(
    tmp_path: Path,
    old: str,
    new: str,
    expected: str,
) -> None:
    config_path = _write_valid_config(tmp_path)
    _add_text_intelligence_config(config_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(old, new, 1),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=expected):
        load_config(config_path)


def test_load_config_rejects_text_intelligence_when_text_disabled(tmp_path: Path) -> None:
    config_path = _write_valid_config(tmp_path)
    _add_text_intelligence_config(config_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("text:\n  enabled: true", "text:\n  enabled: false"),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="text.intelligence.enabled requires text.enabled"):
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
logging:
  output_dir: logs
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
monitor:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _add_derivatives_config(config_path: Path) -> None:
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "      1h: 720\n",
            f"      1h: 720\n{_DERIVATIVES_CONFIG_BLOCK}",
        ),
        encoding="utf-8",
    )


def _add_macro_calendar_config(config_path: Path) -> None:
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "quant:\n",
            """
macro_calendar:
  enabled: true
  source: federal_reserve_fomc
  data_classes:
    - central_bank_event
  regions:
    - US
  lookback_days: 7
  lookahead_days: 45

quant:
""",
        ),
        encoding="utf-8",
    )


def _add_onchain_flow_config(config_path: Path) -> None:
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "quant:\n",
            """
onchain_flow:
  enabled: true
  source: public_aggregate
  data_classes:
    - stablecoin_supply
    - chain_activity
    - network_congestion
    - exchange_flow_availability
  assets:
    - ALL_STABLECOINS
    - BTC
  chains:
    - all
    - bitcoin
  lookback_days: 7

quant:
""",
        ),
        encoding="utf-8",
    )


def _add_user_state_config(config_path: Path) -> None:
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "quant:\n",
            "user_state:\n  enabled: true\n  path: user_state.local.yaml\n\nquant:\n",
        ),
        encoding="utf-8",
    )


def _write_config_text(tmp_path: Path, text: str) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(text.strip(), encoding="utf-8")
    return config_path


def _add_text_intelligence_config(config_path: Path) -> None:
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "text:\n  enabled: true",
            """
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
""".strip(),
        ),
        encoding="utf-8",
    )


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
