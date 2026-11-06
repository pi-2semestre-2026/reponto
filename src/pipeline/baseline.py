"""Moving-average baseline: the reference every model has to beat."""

import pandas as pd

from pipeline.weekly import SERIES_KEYS


def moving_average_forecast(weekly: pd.DataFrame, window: int = 4, horizon: int = 1, value: str = "sales") -> pd.Series:
    """Forecast of week t = mean of the `window` weeks ending at t - horizon.

    The shift comes BEFORE the rolling mean: `rolling(k).mean()` at row t would
    include week t itself (look-ahead leakage). Computed per series, so stores
    and families never mix. Returns a Series aligned with `weekly`'s index;
    the first `window + horizon - 1` weeks of each series are NaN.
    """
    if window < 1 or horizon < 1:
        raise ValueError("window and horizon must be >= 1")
    ordered = weekly.sort_values(SERIES_KEYS + ["week_start"])
    forecast = ordered.groupby(SERIES_KEYS, observed=True, sort=False)[value].transform(
        lambda s: s.shift(horizon).rolling(window).mean()
    )
    return forecast.reindex(weekly.index)
