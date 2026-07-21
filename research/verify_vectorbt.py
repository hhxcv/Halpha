from __future__ import annotations

import json
import platform
import time

import pandas as pd
import vectorbt as vbt


def main() -> None:
    index = pd.date_range("2026-01-01", periods=5, freq="h", tz="UTC")
    close = pd.Series([100.0, 102.0, 104.0, 103.0, 106.0], index=index, name="close")
    raw_entry = pd.Series([False, True, False, False, False], index=index)
    raw_exit = pd.Series([False, False, False, True, False], index=index)
    shifted_entry = raw_entry.vbt.fshift(1)
    shifted_exit = raw_exit.vbt.fshift(1)
    started = time.perf_counter()
    moving_averages = vbt.MA.run(close, window=[2, 3, 4]).ma
    rolling_splits = list(
        vbt.RollingSplitter().split(close, n=2, window_len=4, set_lens=(0.5,))
    )

    trial_returns = pd.DataFrame(
        {
            "a": [0.01, -0.005, 0.008, 0.003, -0.002, 0.006, 0.004, 0.001],
            "b": [0.008, -0.006, 0.009, 0.002, -0.003, 0.007, 0.003, 0.002],
            "c": [0.02, -0.02, 0.015, -0.01, 0.012, -0.005, 0.01, 0.001],
        },
        index=pd.date_range("2026-01-01", periods=8, freq="D", tz="UTC"),
    )
    deflated_sharpe = trial_returns.vbt.returns.deflated_sharpe_ratio(nb_trials=3)

    raw = vbt.Portfolio.from_signals(
        close,
        raw_entry,
        raw_exit,
        init_cash=10_000.0,
        fees=0.001,
        slippage=0.002,
        freq="1h",
    )
    shifted = vbt.Portfolio.from_signals(
        close,
        shifted_entry,
        shifted_exit,
        init_cash=10_000.0,
        fees=0.001,
        slippage=0.002,
        freq="1h",
    )
    no_cost = vbt.Portfolio.from_signals(
        close,
        shifted_entry,
        shifted_exit,
        init_cash=10_000.0,
        fees=0.0,
        slippage=0.0,
        freq="1h",
    )
    elapsed_seconds = time.perf_counter() - started

    raw_timestamps = [str(value) for value in raw.orders.records_readable["Timestamp"]]
    shifted_timestamps = [str(value) for value in shifted.orders.records_readable["Timestamp"]]
    with_costs = float(shifted.total_return())
    without_costs = float(no_cost.total_return())

    assert vbt.__version__ == "1.1.0"
    assert moving_averages.shape == (5, 3)
    assert moving_averages.columns.tolist() == [2, 3, 4]
    assert len(rolling_splits) == 2
    assert [list(part) for part in rolling_splits[0]] == [[0, 1], [2, 3]]
    assert deflated_sharpe.notna().all()
    assert ((deflated_sharpe >= 0.0) & (deflated_sharpe <= 1.0)).all()
    assert raw_timestamps == [str(index[1]), str(index[3])]
    assert shifted_timestamps == [str(index[2]), str(index[4])]
    assert with_costs < without_costs

    print(
        json.dumps(
            {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "vectorbt": vbt.__version__,
                "pandas": pd.__version__,
                "broadcast_moving_average_windows": moving_averages.columns.tolist(),
                "rolling_split_count": len(rolling_splits),
                "deflated_sharpe_ratio": deflated_sharpe.to_dict(),
                "raw_order_timestamps": raw_timestamps,
                "shifted_order_timestamps": shifted_timestamps,
                "shifted_total_return_with_costs": with_costs,
                "shifted_total_return_without_costs": without_costs,
                "framework_checks_elapsed_seconds_including_first_jit": elapsed_seconds,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
