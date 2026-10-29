import math

import pandas as pd
import pytest

from pipeline.baseline import moving_average_forecast
from pipeline.evaluation import evaluate


def series(values, store=1, family="A", start="2016-01-04"):
    weeks = pd.date_range(start, periods=len(values), freq="7D")
    return pd.DataFrame({"store_nbr": store, "family": family, "week_start": weeks, "sales": [float(v) for v in values]})


def as_list(s):
    return [None if math.isnan(v) else v for v in s]


def test_plan_example_k2_h1():
    w = series([10, 20, 30, 40, 50])
    assert as_list(moving_average_forecast(w, window=2, horizon=1)) == [None, None, 15, 25, 35]


def test_changing_week_t_does_not_change_forecast_of_t():
    w = series([10, 20, 30, 40, 50])
    before = moving_average_forecast(w, window=2, horizon=1)
    w.loc[3, "sales"] = 9999
    after = moving_average_forecast(w, window=2, horizon=1)
    assert before[3] == after[3]


def test_k1_is_last_week():
    w = series([3, 1, 4, 1, 5])
    assert as_list(moving_average_forecast(w, window=1, horizon=1)) == [None, 3, 1, 4, 1]


def test_horizon_2_uses_data_up_to_t_minus_2():
    w = series([10, 20, 30, 40, 50])
    assert as_list(moving_average_forecast(w, window=2, horizon=2)) == [None, None, None, 15, 25]


def test_series_are_independent_and_index_aligned():
    w = pd.concat([series([1, 1, 1, 1], store=1), series([100, 100, 100, 100], store=2)], ignore_index=True)
    w = w.sample(frac=1, random_state=0)  # shuffled input order
    f = moving_average_forecast(w, window=2, horizon=1)
    assert (f[w["store_nbr"] == 1].dropna() == 1).all()
    assert (f[w["store_nbr"] == 2].dropna() == 100).all()


def test_evaluate_scores_only_the_test_period():
    w = series([10] * 8 + [20, 20])
    w["forecast"] = 10.0
    per_series, residuals = evaluate(w, test_weeks=2)
    assert per_series.loc[0, "points"] == 2
    assert per_series.loc[0, "mae"] == 10
    assert per_series.loc[0, "mape"] == pytest.approx(50.0)
    assert list(residuals["error"]) == [10.0, 10.0]
