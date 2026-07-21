import importlib.util
import math
import sys
import tempfile
import threading
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "monitor.py"
SPEC = importlib.util.spec_from_file_location("btc_monitor", MODULE_PATH)
monitor = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = monitor
SPEC.loader.exec_module(monitor)


class MonitorTests(unittest.TestCase):
    def test_cutoff_is_last_closed_utc_day(self):
        cutoff = monitor.latest_closed_cutoff(datetime(2026, 7, 21, 13, 4, tzinfo=UTC))
        self.assertEqual(cutoff.isoformat(), "2026-07-20T23:59:59.999000+00:00")

    def test_normalize_drops_open_invalid_and_duplicates(self):
        cutoff_ms = 2 * monitor.DAY_MS - 1
        valid = [0, "1", "2", "0.5", "1.5", "3", monitor.DAY_MS - 1, "4", 5, "1", "1", "0"]
        duplicate = [0, "1", "2", "0.5", "1.6", "3", monitor.DAY_MS - 1, "4", 5, "1", "1", "0"]
        open_bar = [monitor.DAY_MS, "1", "2", "0.5", "1.5", "3", 3 * monitor.DAY_MS, "4", 5, "1", "1", "0"]
        frame, quality = monitor.normalize_binance_klines([valid, duplicate, open_bar], cutoff_ms)
        self.assertEqual(len(frame), 1)
        self.assertAlmostEqual(frame.iloc[0]["close"], 1.6)
        self.assertEqual(quality["duplicate_rows"], 1)
        self.assertEqual(quality["open_rows"], 1)

    def test_aligned_returns_do_not_bridge_missing_days(self):
        index = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-04"], utc=True)
        asset = pd.Series([100, 110, 121], index=index)
        btc = pd.Series([100, 105, 110], index=index)
        returns = monitor.aligned_daily_returns(asset, btc)
        self.assertEqual(len(returns), 1)
        self.assertEqual(returns.index[0], index[1])

    def test_analysis_recovers_beta_and_strong_rule(self):
        rng = np.random.default_rng(17)
        index = pd.date_range("2025-01-01", periods=500, freq="D", tz="UTC")
        btc_ret = rng.normal(0, 0.02, len(index) - 1)
        asset_ret = 1.4 * btc_ret + rng.normal(0, 0.004, len(index) - 1)
        btc = pd.Series(np.r_[100, 100 * np.exp(np.cumsum(btc_ret))], index=index)
        asset = pd.Series(np.r_[50, 50 * np.exp(np.cumsum(asset_ret))], index=index)
        result, rolling = monitor.analyze_pair("TESTUSDT", asset, btc)
        self.assertEqual(result["status"], "ANALYZED")
        self.assertAlmostEqual(result["beta"], 1.4, delta=0.05)
        self.assertGreater(result["pearson"], 0.9)
        self.assertFalse(rolling.empty)
        monitor.apply_multiple_testing([result])
        self.assertTrue(result["statistically_significant"])
        self.assertTrue(result["strong_association"])

    def test_universe_filter_excludes_non_crypto_exposure(self):
        rows = [
            ["2026-01-01T00:00:00Z", "BINANCE_SPOT", "BTCUSDT", "TRADING", "True", "BTC", "USDT", "CRYPTO_ANCHOR", "EXPLICIT", "Layer-1"],
            ["2026-01-01T00:00:00Z", "BINANCE_SPOT", "ETHUSDT", "TRADING", "True", "ETH", "USDT", "CRYPTO_ANCHOR", "EXPLICIT", "Layer-1"],
            ["2026-01-01T00:00:00Z", "BINANCE_SPOT", "DOGEUSDT", "TRADING", "True", "DOGE", "USDT", "CRYPTO_NATIVE", "DEFAULT_CRYPTO_NATIVE_AFTER_EXPLICIT_EXCLUSIONS", "Meme"],
            ["2026-01-01T00:00:00Z", "BINANCE_SPOT", "DGBUSDT", "TRADING", "True", "DGB", "USDT", "CRYPTO_NATIVE", "DEFAULT_CRYPTO_NATIVE_AFTER_EXPLICIT_EXCLUSIONS", ""],
            ["2026-01-01T00:00:00Z", "BINANCE_SPOT", "NVDABUSDT", "TRADING", "True", "NVDAB", "USDT", "CRYPTO_NATIVE", "DEFAULT_CRYPTO_NATIVE_AFTER_EXPLICIT_EXCLUSIONS", ""],
            ["2026-01-01T00:00:00Z", "BINANCE_SPOT", "USDCUSDT", "TRADING", "True", "USDC", "USDT", "STABLE_OR_FIAT_RELATIVE", "EXPLICIT", ""],
        ]
        columns = ["snapshot_time_utc", "market", "symbol", "status", "currently_trading", "base_asset", "quote_asset", "economic_exposure", "economic_exposure_source", "classification_subtypes"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "universe.csv"
            pd.DataFrame(rows, columns=columns).to_csv(path, index=False)
            selected, identity = monitor.load_universe(path)
        self.assertEqual(selected["symbol"].tolist(), ["BTCUSDT", "DGBUSDT", "DOGEUSDT", "ETHUSDT"])
        self.assertEqual(identity["eligible_objects"], 3)
        self.assertEqual(identity["excluded_bstock_symbols"], ["NVDABUSDT"])

    def test_server_binds_before_initial_refresh(self):
        events = []
        refresh_started = threading.Event()

        class FakeServer:
            def __init__(self, address, handler):
                events.append("server_bound")

            def serve_forever(self):
                self.started_in_time = refresh_started.wait(timeout=1)

            def server_close(self):
                events.append("server_closed")

        def fake_refresh(*args, **kwargs):
            events.append("refresh_started")
            refresh_started.set()
            return {}

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(monitor, "ThreadingHTTPServer", FakeServer), patch.object(monitor, "refresh", fake_refresh):
                monitor.serve("127.0.0.1", 8766, Path(directory), 900, 1, False)

        self.assertTrue(refresh_started.is_set())
        self.assertLess(events.index("server_bound"), events.index("refresh_started"))
        self.assertEqual(events[-1], "server_closed")


if __name__ == "__main__":
    unittest.main()
