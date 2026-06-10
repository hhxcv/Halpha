from importlib import metadata, util


def test_quant_runtime_dependencies_are_installed() -> None:
    packages = {
        "ccxt": "ccxt",
        "pandas": "pandas",
        "pyarrow": "pyarrow",
        "vectorbt": "vectorbt",
    }

    for package, module in packages.items():
        assert metadata.version(package)
        assert util.find_spec(module) is not None


def test_quant_runtime_dependencies_basic_local_capabilities() -> None:
    import ccxt
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq

    assert "binance" in ccxt.exchanges

    frame = pd.DataFrame(
        [
            {"open_time": "2026-06-01T00:00:00Z", "close": 100.0},
            {"open_time": "2026-06-02T00:00:00Z", "close": 101.0},
        ]
    )
    table = pa.Table.from_pandas(frame)

    assert table.num_rows == 2
    assert callable(pq.write_table)
