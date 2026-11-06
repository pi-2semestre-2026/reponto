import math

import pytest

from pipeline import metrics


def test_plan_example():
    y, yhat = [100, 200], [110, 180]
    assert metrics.mae(y, yhat) == 15
    value, ignored = metrics.mape(y, yhat)
    assert value == pytest.approx(10.0) and ignored == 0


def test_perfect_forecast_is_zero():
    y = [5, 7, 9]
    assert metrics.mae(y, y) == 0
    assert metrics.mape(y, y) == (0.0, 0)
    assert metrics.wape(y, y) == 0
    assert metrics.bias(y, y) == 0


def test_zero_actual_is_ignored_in_mape_and_counted():
    value, ignored = metrics.mape([0, 100], [10, 110])
    assert ignored == 1
    assert value == pytest.approx(10.0)


def test_all_zero_actual_gives_nan_mape():
    value, ignored = metrics.mape([0, 0], [1, 2])
    assert math.isnan(value) and ignored == 2


def test_wape_and_bias_match_simulator_definition():
    y, yhat = [100, 200], [110, 180]
    assert metrics.wape(y, yhat) == pytest.approx(30 / 300 * 100)
    assert metrics.bias(y, yhat) == pytest.approx(-10 / 300 * 100)


def test_mape_is_asymmetric():
    under, _ = metrics.mape([100], [0])
    over, _ = metrics.mape([100], [300])
    assert under == 100 and over == 200


def test_nan_is_rejected():
    with pytest.raises(ValueError):
        metrics.mae([1, float("nan")], [1, 2])
