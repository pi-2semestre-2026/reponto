"""Pure demand math shared by the recommender and the simulator brain.

Two ideas make the recommendation adapt to EACH store:

1. Weekday profile (the store's own rhythm). For every product we measure how
   its sales on each weekday compare with its daily average, using only the
   store's own history. Few observations are unreliable, so the estimate is
   shrunk towards a prior: product -> whole store (receipts per weekday) ->
   public dataset pattern (LightGBM). With k pseudo-weeks of prior evidence:

       index_w = (n_w * own_w + k * prior_w) / (n_w + k),   mean(index) = 1

   A store that sells more of a product on Mondays gets a Monday index > 1,
   so the days before Monday need more stock.

2. Safety stock from the forecast error. Over the observed days we compare
   what sold with what the profile predicted (rate x index of that weekday).
   The standard deviation of that error, scaled to the protection period,
   gives the margin for a ~95% service level:

       safety = z * sigma_daily * sqrt(cycle_days)

   Products that are harder to predict get a larger margin. With fewer than
   MIN_DAYS_FOR_ERROR observed days, the fixed rule (30% of the cycle) is used.

Stock levels follow an order-up-to policy over the next `cycle` days:
   reorder point (min) = demand of the next 0.4 x cycle days + safety
   recommended level   = 1.2 x demand of the cycle + safety
   maximum             = 2.0 x demand of the cycle + safety
With a flat profile and the fixed safety rule these reduce exactly to the
previous formulas.
"""

import datetime as dt
import math
import statistics

WEEKDAY_NAMES = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
WEEKDAY_SHORT = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
WEEKDAY_PLURAL = ("às segundas", "às terças", "às quartas", "às quintas", "às sextas", "aos sábados", "aos domingos")

PRODUCT_SHRINK_K = 4.0
STORE_SHRINK_K = 2.0
Z_SERVICE = 1.65
SERVICE_LEVEL_PCT = 95
MIN_DAYS_FOR_ERROR = 14
MIN_DAYS_FOR_PROFILE = 14
FALLBACK_SAFETY_SHARE = 0.3
REORDER_SHARE = 0.4
TARGET_MULT = 1.2
MAX_MULT = 2.0
FLAT = [1.0] * 7


def daily_series(day_totals: dict, start: dt.date, end: dt.date) -> list[tuple[dt.date, float]]:
    """Every day in [start, end] with its total (zero-filled)."""
    if end < start:
        return []
    days = (end - start).days + 1
    return [(start + dt.timedelta(days=i), float(day_totals.get(start + dt.timedelta(days=i), 0.0))) for i in range(days)]


def weekday_profile(series: list[tuple[dt.date, float]], prior: list[float], k: float) -> list[float]:
    sums = [0.0] * 7
    counts = [0] * 7
    for day, qty in series:
        w = day.weekday()
        sums[w] += qty
        counts[w] += 1
    total = sum(sums)
    if not series or total <= 0:
        return list(prior)
    overall = total / len(series)
    index = []
    for w in range(7):
        own = (sums[w] / counts[w]) / overall if counts[w] else prior[w]
        index.append((counts[w] * own + k * prior[w]) / (counts[w] + k))
    mean = sum(index) / 7
    return [v / mean for v in index] if mean > 0 else list(prior)


def project(rate: float, index: list[float], start: dt.date, days: int) -> list[float]:
    return [rate * index[(start + dt.timedelta(days=d)).weekday()] for d in range(days)]


def partial_sum(values: list[float], length: float) -> float:
    """Sum of the first `length` days, fractional last day included."""
    full = int(length)
    frac = length - full
    total = sum(values[:full])
    if frac > 0 and full < len(values):
        total += frac * values[full]
    return total


def safety_stock(series, rate: float, index: list[float], cycle: int, cycle_demand: float) -> dict:
    if len(series) >= MIN_DAYS_FOR_ERROR and rate > 0:
        residuals = [qty - rate * index[day.weekday()] for day, qty in series]
        sigma = statistics.pstdev(residuals)
        safety = min(Z_SERVICE * sigma * math.sqrt(cycle), cycle_demand)
        return {"safety": safety, "method": "erro", "sigma": sigma}
    return {"safety": FALLBACK_SAFETY_SHARE * cycle_demand, "method": "regra", "sigma": None}


def stock_levels(rate: float, index: list[float], today: dt.date, cycle: int, series) -> dict:
    projection = project(rate, index, today, cycle)
    cycle_demand = sum(projection)
    reorder_demand = partial_sum(projection, REORDER_SHARE * cycle)
    s = safety_stock(series, rate, index, cycle, cycle_demand)
    return {
        "projection": projection,
        "cycle_demand": cycle_demand,
        "reorder_demand": reorder_demand,
        "reorder_days": REORDER_SHARE * cycle,
        "safety_stock": s["safety"],
        "safety_method": s["method"],
        "sigma_daily": s["sigma"],
        "min_stock": reorder_demand + s["safety"],
        "recommended_quantity": TARGET_MULT * cycle_demand + s["safety"],
        "max_stock": MAX_MULT * cycle_demand + s["safety"],
    }


def dataset_weekday_prior(model, month: int, size_bucket: int) -> list[float]:
    """Weekday shape of the public dataset for this month and store size."""
    preds = [model.predict(month, w, size_bucket) for w in range(7)]
    if any(p is None for p in preds):
        return list(FLAT)
    mean = sum(preds) / 7
    return [p / mean for p in preds] if mean > 0 else list(FLAT)


def month_factor(model, month: int, size_bucket: int, bounds=(0.5, 2.0)) -> float | None:
    """Seasonal level of the month (weekday effect averaged out)."""
    preds = [model.predict(month, w, size_bucket) for w in range(7)]
    if any(p is None for p in preds) or not model.overall_mean:
        return None
    factor = (sum(preds) / 7) / model.overall_mean
    return max(bounds[0], min(bounds[1], factor))


def peak_summary(index: list[float]) -> dict:
    w = max(range(7), key=lambda i: index[i])
    low = min(range(7), key=lambda i: index[i])
    return {
        "peak_weekday": w,
        "peak_name": WEEKDAY_NAMES[w],
        "peak_phrase": WEEKDAY_PLURAL[w],
        "peak_pct": round((index[w] - 1) * 100),
        "low_weekday": low,
        "low_name": WEEKDAY_NAMES[low],
        "low_pct": round((index[low] - 1) * 100),
    }
