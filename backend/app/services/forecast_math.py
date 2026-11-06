"""Pure demand math shared by the recommender, the simulator brain and the lab.

1. Weekday profile (the store's own rhythm — "cerveja vende pouco na terça e
   muito no sábado"). For every product we measure how its sales on each
   weekday compare with its daily average, using the store's own history with
   RECENT WEEKS WEIGHING MORE (half-life PROFILE_HALF_LIFE_DAYS), so a change
   in habits ("jogo toda quarta") is picked up in a few weeks. Few observations
   are unreliable, so the estimate is shrunk towards a prior:

       index_w = (n_w * own_w + k * prior_w) / (n_w + k),   mean(index) = 1

   with n_w the (decay-weighted) number of weeks seen for weekday w. The prior
   is the product's CATEGORY pattern (learned from real supermarket data)
   adjusted to the store's own rhythm (store / typical store), so a beer starts
   from "beverages peak at the weekend" and a store closed on Sundays starts
   with no Sunday sales. Chosen on Favorita (scripts/experimentos/
   perfil_dia_semana.py): on the test year it cuts the daily error by 45%
   versus "same every day" and 27% versus a single pattern for everyone.

2. Service level. Products that spoil before the next delivery (bread, fruit)
   follow the newsvendor rule: the right chance of not running out is
   Cu / (Cu + Co), where a loaf too many costs its purchase cost (thrown away,
   Co) and a loaf too few costs the margin plus the risk of losing the
   customer (Cu = margin + GOODWILL_SHARE x price). Everything else aims at 95%.

3. Safety stock from the forecast error, sized for the cycle:
     - rule path:  z(level) x sigma_daily x sqrt(cycle)
     - model path: the weekly model's calibrated quantile, split into a level
       error (same direction all week, grows with cycle/7) and daily noise
       (independent, grows with sqrt(cycle)), so daily restocking is not
       oversized and monthly restocking is not undersized.

4. Censored demand. On a day the product SOLD OUT, the recorded sales are
   only what was on the shelf, not what customers wanted. Learning from them
   as if they were demand pulls the forecast down, the next order is smaller,
   it sells out again — a spiral. Those days are "unconstrained": the system
   assumes demand was STOCKOUT_UPLIFT above the recorded sales.

Stock levels follow an order-up-to policy over the next `cycle` days.
"""

import datetime as dt
import math
import statistics
from statistics import NormalDist

WEEKDAY_NAMES = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
WEEKDAY_SHORT = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
WEEKDAY_PLURAL = ("às segundas", "às terças", "às quartas", "às quintas", "às sextas", "aos sábados", "aos domingos")

PROFILE_HALF_LIFE_DAYS = 42.0
PRODUCT_SHRINK_K = 2.0
STORE_SHRINK_K = 2.0
Z_SERVICE = 1.65
SERVICE_LEVEL_PCT = 95
DEFAULT_SERVICE = 0.95
MIN_SERVICE = 0.50
PERISHABLE_FALLBACK_SERVICE = 0.80
GOODWILL_SHARE = 0.5
MIN_DAYS_FOR_ERROR = 14
MIN_DAYS_FOR_PROFILE = 14
FALLBACK_SAFETY_SHARE = 0.3
REORDER_SHARE = 0.4
TARGET_MULT = 1.2
MAX_MULT = 2.0
FLAT = [1.0] * 7
STOCKOUT_UPLIFT = 0.25


def uncensor(qty: float, sold_out: bool) -> float:
    """Demand estimate for one day: recorded sales, or more if the shelf ran empty."""
    return qty * (1.0 + STOCKOUT_UPLIFT) + 1.0 if sold_out and qty > 0 else qty

# Typical shelf life (days) of perishable categories. A product spoils before the
# next delivery when shelf life <= replenishment cycle.
SHELF_LIFE_DAYS = {
    "Padaria": 1,
    "Peixes e Frutos do Mar": 2,
    "Carnes e Aves": 3,
    "Hortifrúti": 5,
}


def daily_series(day_totals: dict, start: dt.date, end: dt.date) -> list[tuple[dt.date, float]]:
    """Every day in [start, end] with its total (zero-filled)."""
    if end < start:
        return []
    days = (end - start).days + 1
    return [(start + dt.timedelta(days=i), float(day_totals.get(start + dt.timedelta(days=i), 0.0))) for i in range(days)]


def weekday_profile(series: list[tuple[dt.date, float]], prior: list[float], k: float, half_life_days: float = PROFILE_HALF_LIFE_DAYS) -> list[float]:
    """Decay-weighted weekday index shrunk towards `prior` (mean 1)."""
    if not series:
        return list(prior)
    last = max(day for day, _ in series)
    sums = [0.0] * 7
    weights = [0.0] * 7
    total_q = total_w = 0.0
    for day, qty in series:
        w_age = 2.0 ** (-((last - day).days) / half_life_days)
        wd = day.weekday()
        sums[wd] += w_age * qty
        weights[wd] += w_age
        total_q += w_age * qty
        total_w += w_age
    if total_q <= 0:
        return list(prior)
    overall = total_q / total_w
    index = []
    for wd in range(7):
        own = (sums[wd] / weights[wd]) / overall if weights[wd] else prior[wd]
        index.append((weights[wd] * own + k * prior[wd]) / (weights[wd] + k))
    mean = sum(index) / 7
    return [v / mean for v in index] if mean > 0 else list(prior)


def category_store_prior(category_index: list[float], store_index: list[float], typical_index: list[float]) -> list[float]:
    """Category pattern adjusted to how this store differs from a typical store."""
    raw = [c * s / t if t > 0 else c for c, s, t in zip(category_index, store_index, typical_index)]
    mean = sum(raw) / 7
    return [v / mean for v in raw] if mean > 0 else list(category_index)


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


# ---------------------------------------------------------------- service level


def service_target(category: str | None, cycle: int, price: float | None, cost: float | None) -> dict:
    """Target probability of not running out during the cycle.

    Spoils before the next delivery -> newsvendor: Cu / (Cu + Co) with
    Cu = margin + goodwill and Co = cost (clamped to [MIN_SERVICE, 95%]).
    Otherwise the leftover is sold later, so the target is 95%.
    """
    shelf = SHELF_LIFE_DAYS.get(category or "")
    if shelf is None or shelf > cycle:
        return {"level": DEFAULT_SERVICE, "perishable": False, "shelf_life_days": shelf, "rule": "padrao"}
    price = float(price or 0)
    cost = float(cost or 0)
    if price > 0 and 0 < cost < price:
        underage = (price - cost) + GOODWILL_SHARE * price
        level = min(DEFAULT_SERVICE, max(MIN_SERVICE, underage / (underage + cost)))
        rule = "jornaleiro"
    else:
        level = PERISHABLE_FALLBACK_SERVICE
        rule = "jornaleiro_sem_custo"
    return {"level": level, "perishable": True, "shelf_life_days": shelf, "rule": rule}


def z_for(level: float) -> float:
    return NormalDist().inv_cdf(min(0.999, max(0.001, level)))


def daily_sigma(series, rate: float, index: list[float]) -> float | None:
    if len(series) >= MIN_DAYS_FOR_ERROR and rate > 0:
        return statistics.pstdev([qty - rate * index[day.weekday()] for day, qty in series])
    return None


def safety_stock(series, rate: float, index: list[float], cycle: int, cycle_demand: float, level: float = DEFAULT_SERVICE) -> dict:
    sigma = daily_sigma(series, rate, index)
    if sigma is not None:
        safety = min(z_for(level) * sigma * math.sqrt(cycle), cycle_demand)
        return {"safety": safety, "method": "erro", "sigma": sigma}
    share = FALLBACK_SAFETY_SHARE if level >= DEFAULT_SERVICE else FALLBACK_SAFETY_SHARE * max(0.0, z_for(level)) / Z_SERVICE
    return {"safety": share * cycle_demand, "method": "regra", "sigma": None}


def stock_levels(rate: float, index: list[float], today: dt.date, cycle: int, series, level: float = DEFAULT_SERVICE) -> dict:
    projection = project(rate, index, today, cycle)
    cycle_demand = sum(projection)
    reorder_demand = partial_sum(projection, REORDER_SHARE * cycle)
    s = safety_stock(series, rate, index, cycle, cycle_demand, level)
    target_mult = TARGET_MULT if level >= DEFAULT_SERVICE else 1.0
    return {
        "projection": projection,
        "cycle_demand": cycle_demand,
        "reorder_demand": reorder_demand,
        "reorder_days": REORDER_SHARE * cycle,
        "safety_stock": s["safety"],
        "safety_method": s["method"],
        "sigma_daily": s["sigma"],
        "service_level": level,
        "min_stock": reorder_demand + s["safety"],
        "recommended_quantity": max(0.0, target_mult * cycle_demand + s["safety"]),
        "max_stock": MAX_MULT * cycle_demand + max(0.0, s["safety"]),
    }


def quantile_at(quantiles: dict, level: float) -> float:
    """Upper multiplier (actual / forecast) at `level`, interpolated between calibrated levels."""
    points = sorted((float(k), float(v)) for k, v in quantiles.items())
    if not points:
        return 1.0 + (z_for(level) / Z_SERVICE) * 0.5
    if level <= points[0][0]:
        return points[0][1]
    for (l0, q0), (l1, q1) in zip(points, points[1:]):
        if level <= l1:
            return q0 + (q1 - q0) * (level - l0) / (l1 - l0)
    return points[-1][1]


def model_stock_levels(rate: float, index: list[float], today: dt.date, cycle: int, forecast: dict, series=None, level: float = DEFAULT_SERVICE) -> dict:
    """Order-up-to levels when the validated weekly model is in charge.

    h7 = q(level) - 1 is the calibrated half-width for one week. It is split
    into a level error L (correlated: grows with cycle/7) and the product's own
    daily noise (independent: z x sigma x sqrt(cycle)):
        L^2 = (W h7)^2 - (z sigma sqrt 7)^2
        safety = sqrt((L cycle/7)^2 + (z sigma)^2 cycle)
    For cycle = 7 this is exactly W h7, the calibrated bound.
    recommended = demand of the cycle + safety (no extra cushion: the forecast is unbiased).
    """
    projection = project(rate, index, today, cycle)
    cycle_demand = sum(projection)
    reorder_demand = partial_sum(projection, REORDER_SHARE * cycle)
    weekly = forecast["weekly"]
    h7 = quantile_at(forecast.get("quantiles") or {}, level) - 1.0
    sigma = daily_sigma(series or [], rate, index)
    sign = 1.0 if h7 >= 0 else -1.0
    if sigma is not None:
        z = abs(z_for(level))
        level_part = math.sqrt(max(0.0, (weekly * h7) ** 2 - (z * sigma * math.sqrt(7)) ** 2))
        safety = sign * math.sqrt((level_part * cycle / 7.0) ** 2 + (z * sigma) ** 2 * cycle)
    else:
        safety = weekly * h7 * math.sqrt(cycle / 7.0)
    return {
        "projection": projection,
        "cycle_demand": cycle_demand,
        "reorder_demand": reorder_demand,
        "reorder_days": REORDER_SHARE * cycle,
        "safety_stock": safety,
        "safety_method": "modelo",
        "sigma_daily": sigma,
        "service_level": level,
        "min_stock": max(0.0, reorder_demand + safety),
        "recommended_quantity": max(0.0, cycle_demand + safety),
        "max_stock": MAX_MULT * cycle_demand + max(0.0, safety),
    }


# ---------------------------------------------------------------- dataset shapes


def dataset_weekday_prior(model, month: int, size_bucket: int, category: str | None = None) -> list[float]:
    """Weekday shape of the public dataset for this month, store size and category
    (category None = the typical store, all categories)."""
    preds = [model.predict(month, w, size_bucket, category) for w in range(7)]
    if any(p is None for p in preds):
        return list(FLAT)
    mean = sum(preds) / 7
    return [p / mean for p in preds] if mean > 0 else list(FLAT)


def month_factor(model, month: int, size_bucket: int, bounds=(0.5, 2.0), category: str | None = None) -> float | None:
    """Seasonal level of the month relative to the category's yearly mean (weekday effect averaged out)."""
    preds = [model.predict(month, w, size_bucket, category) for w in range(7)]
    reference = model.reference_mean(size_bucket, category) if model.ready else None
    if any(p is None for p in preds) or not reference:
        return None
    factor = (sum(preds) / 7) / reference
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
        "low_phrase": WEEKDAY_PLURAL[low],
        "low_pct": round((index[low] - 1) * 100),
    }
