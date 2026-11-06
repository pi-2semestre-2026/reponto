"""Forecast error metrics.

Error convention: e = y - yhat (actual minus forecast). WAPE and bias use the
same definitions as the app simulator (backend/simulator/metrics.py,
`_aggregate`), so numbers from the pipeline and from the app are comparable.

All functions expect aligned arrays without NaN; the caller drops weeks that
have no forecast. Percent metrics are returned in percent (10.0 means 10%).
"""

import numpy as np


def _arrays(y, yhat) -> tuple[np.ndarray, np.ndarray]:
    y = np.asarray(y, dtype=float)
    yhat = np.asarray(yhat, dtype=float)
    if y.shape != yhat.shape:
        raise ValueError("y and yhat must have the same length")
    if np.isnan(y).any() or np.isnan(yhat).any():
        raise ValueError("NaN in y or yhat: drop rows without forecast first")
    return y, yhat


def mae(y, yhat) -> float:
    """Mean absolute error, in the unit of the series."""
    y, yhat = _arrays(y, yhat)
    return float(np.abs(y - yhat).mean()) if len(y) else float("nan")


def mape(y, yhat) -> tuple[float, int]:
    """Mean absolute percentage error, in percent.

    Undefined when the actual is zero, so those weeks are left out.
    Returns (mape_pct, n_ignored) so the caller can report how many were skipped.
    """
    y, yhat = _arrays(y, yhat)
    nonzero = y != 0
    ignored = int((~nonzero).sum())
    if not nonzero.any():
        return float("nan"), ignored
    return float((np.abs(y[nonzero] - yhat[nonzero]) / np.abs(y[nonzero])).mean() * 100), ignored


def wape(y, yhat) -> float:
    """Weighted absolute percentage error: sum|e| / sum(y), in percent."""
    y, yhat = _arrays(y, yhat)
    total = y.sum()
    return float(np.abs(y - yhat).sum() / total * 100) if total else float("nan")


def bias(y, yhat) -> float:
    """sum(yhat - y) / sum(y), in percent. Positive = forecast above actual."""
    y, yhat = _arrays(y, yhat)
    total = y.sum()
    return float((yhat - y).sum() / total * 100) if total else float("nan")
