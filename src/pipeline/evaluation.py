"""Evaluation protocol shared by Phase 1 (baseline) and Phase 2 (LightGBM).

Test period = the last `test_weeks` complete weeks. Every forecast in it must
have been produced with data up to the previous week (rolling origin); the
forecast functions guarantee that, this module only scores.
"""

import pandas as pd

from pipeline import metrics
from pipeline.config import TEST_WEEKS
from pipeline.weekly import SERIES_KEYS


def test_period(weekly: pd.DataFrame, test_weeks: int = TEST_WEEKS) -> list[pd.Timestamp]:
    """The last `test_weeks` week_start values present in the data."""
    weeks = sorted(weekly["week_start"].unique())
    if len(weeks) <= test_weeks:
        raise ValueError(f"need more than {test_weeks} weeks, got {len(weeks)}")
    return [pd.Timestamp(w) for w in weeks[-test_weeks:]]


def evaluate(weekly: pd.DataFrame, forecast_col: str = "forecast", test_weeks: int = TEST_WEEKS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Score `forecast_col` against `sales` over the test period.

    Returns:
      per_series: one row per series with mae, mape, mape_ignored, wape, bias, points;
      residuals:  week-by-week test rows with error = sales - forecast
                  (input of Phase 4, where safety stock comes from the error spread).
    """
    period = test_period(weekly, test_weeks)
    test = weekly[weekly["week_start"].isin(period)].dropna(subset=[forecast_col])
    rows = []
    for key, g in test.groupby(SERIES_KEYS, observed=True, sort=True):
        y, yhat = g["sales"].to_numpy(), g[forecast_col].to_numpy()
        mape_value, ignored = metrics.mape(y, yhat)
        rows.append(
            {
                "store_nbr": key[0],
                "family": key[1],
                "mae": metrics.mae(y, yhat),
                "mape": mape_value,
                "mape_ignored": ignored,
                "wape": metrics.wape(y, yhat),
                "bias": metrics.bias(y, yhat),
                "points": len(g),
            }
        )
    per_series = pd.DataFrame(rows)
    residuals = test[SERIES_KEYS + ["week_start", "sales", forecast_col]].rename(columns={forecast_col: "forecast"})
    residuals = residuals.assign(error=residuals["sales"] - residuals["forecast"]).reset_index(drop=True)
    return per_series, residuals
