from __future__ import annotations

import pandas as pd
import pytest

from halpha.quant.regime_filters import realized_volatility_filter_contexts


def test_realized_volatility_filter_contexts_mark_pass_and_suppression() -> None:
    close = pd.Series([100.0, 101.0, 102.0, 120.0])

    contexts = realized_volatility_filter_contexts(
        close,
        timeframe="1d",
        window=2,
        max_realized_volatility_pct=20.0,
    )

    assert contexts[0]["status"] == "insufficient_data"
    assert contexts[1]["status"] == "insufficient_data"
    assert contexts[2]["status"] == "passed"
    assert contexts[2]["suppressed"] is False
    assert contexts[2]["suppression_reason"] is None
    assert contexts[3]["status"] == "suppressed"
    assert contexts[3]["suppressed"] is True
    assert contexts[3]["suppression_reason"] == "realized_volatility_above_max"
    assert contexts[3]["realized_volatility_pct"] > 20.0
    assert contexts[3]["lookahead_policy"] == "closed_bar_no_lookahead"


def test_realized_volatility_filter_contexts_validate_params() -> None:
    close = pd.Series([100.0, 101.0, 102.0])

    with pytest.raises(ValueError, match="window must be a positive integer"):
        realized_volatility_filter_contexts(
            close,
            timeframe="1d",
            window=0,
            max_realized_volatility_pct=20.0,
        )
    with pytest.raises(ValueError, match="max_realized_volatility_pct must be a positive number"):
        realized_volatility_filter_contexts(
            close,
            timeframe="1d",
            window=2,
            max_realized_volatility_pct=0.0,
        )
