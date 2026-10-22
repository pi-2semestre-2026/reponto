"""The player's brain: an exact in-memory replica of the REAL Reponto math.

Uses the same constants, the same blend formula and the same LightGBM
artifact (`app.services.ml.rate_model`, trained at backend boot) as
`app/services/recommender.py`. The only difference: history lives in a
dict instead of Postgres, so the simulation runs hundreds of days in
milliseconds without touching user data.

prior_rate    = baseline(category) × seasonal_factor(LightGBM) × customers/day
observed_rate = Σ qty·2^(−age/half_life) / Σ day_weights   (window from
                first sale, capped to OBS_WINDOW_DAYS)
alpha         = max(0.3, n_sales/(n_sales+10))   (n=0 → stock/cycle trick)
final_rate    = α·observed + (1−α)·prior
levels        = same day-by-day projection with the weekday profile and the
                same error-based safety stock (app.services.forecast_math).
"""

import datetime as dt

from app.config import get_settings
from app.services import forecast_math as fm
from app.services.ml import rate_model
from app.services.seed_data import baseline_by_name, size_bucket_from_customers

DEFAULT_PRIOR = 0.08
SEASONAL_FACTOR_BOUNDS = (0.5, 2.0)


def decay_weight(age_days: float, half_life: float) -> float:
    return 2.0 ** (-age_days / half_life)


def window_denominator(window_days: int, half_life: float) -> float:
    if window_days < 0:
        window_days = 0
    r = 2.0 ** (-1.0 / half_life)
    return (1.0 - r ** (window_days + 1)) / (1.0 - r)


class SimRecommender:
    """Replicates compute_prior_rate + compute_blend for virtual products."""

    def __init__(self, customers_per_day: int, cycle_days: int) -> None:
        self.customers_per_day = customers_per_day
        self.cycle_days = max(1, cycle_days)
        settings = get_settings()
        self.half_life = float(settings.EMA_HALF_LIFE_DAYS)
        self.obs_window = int(settings.OBS_WINDOW_DAYS)
        self.size_bucket = size_bucket_from_customers(customers_per_day)

    def prior_rate(self, category: str, today: dt.date) -> tuple[float, str, float | None]:
        baseline = baseline_by_name(category)
        factor = fm.month_factor(rate_model, today.month, self.size_bucket, SEASONAL_FACTOR_BOUNDS)
        if factor is not None:
            return baseline * factor * self.customers_per_day, "model", round(factor, 3)
        return baseline * self.customers_per_day, "default", None

    def observed_rate(
        self, history: dict[dt.date, tuple[float, int]], today: dt.date, stock: float
    ) -> tuple[float, int, dict]:
        """`history[date] = (units_sold, n_transactions)` — the recommender
        weights UNITS but counts SALES (receipts) for alpha, exactly like
        the real system."""
        cycle = self.cycle_days
        sale_days = sorted(d for d, (qty, _) in history.items() if qty > 0)
        if not sale_days:
            observed = stock / cycle if stock > 0 else 0.0
            return observed, 0, {"window_days": 0, "window_start": today}

        window_start = max(sale_days[0], today - dt.timedelta(days=self.obs_window))
        window_days = (today - window_start).days
        numerator = 0.0
        n_sales = 0
        for d in sale_days:
            if d < window_start or d > today:
                continue
            age = (today - d).days
            qty, n_tx = history[d]
            numerator += qty * decay_weight(age, self.half_life)
            n_sales += n_tx
        denominator = window_denominator(window_days, self.half_life)
        observed = numerator / denominator if denominator > 0 else 0.0
        return observed, n_sales, {"window_days": window_days, "window_start": window_start}

    def recommend(
        self,
        product: dict,
        history: dict[dt.date, tuple[float, int]],
        today: dt.date,
        stock: float,
        store_history: dict[dt.date, float] | None = None,
    ) -> dict:
        prior, source, seasonal = self.prior_rate(product["category"], today)
        observed, n_sales, win = self.observed_rate(history, today, stock)

        if n_sales == 0:
            alpha = 0.3
        else:
            alpha = max(0.3, n_sales / (n_sales + 10))

        final = alpha * observed + (1 - alpha) * prior
        cycle = self.cycle_days

        window_start = win["window_start"]
        yesterday = today - dt.timedelta(days=1)
        dataset_index = fm.dataset_weekday_prior(rate_model, today.month, self.size_bucket)
        store_index = dataset_index
        if store_history:
            first = min(store_history)
            store_series = fm.daily_series(store_history, max(first, window_start), yesterday)
            if len(store_series) >= fm.MIN_DAYS_FOR_PROFILE:
                store_index = fm.weekday_profile(store_series, dataset_index, fm.STORE_SHRINK_K)
        series = fm.daily_series({d: q for d, (q, _) in history.items()}, window_start, yesterday) if n_sales else []
        if len(series) >= fm.MIN_DAYS_FOR_PROFILE:
            weekday_index = fm.weekday_profile(series, store_index, fm.PRODUCT_SHRINK_K)
        else:
            weekday_index = list(store_index)

        levels = fm.stock_levels(final, weekday_index, today, cycle, series)
        confidence = "baixa" if n_sales < 3 else ("media" if n_sales < 10 else "alta")

        return {
            "prior_rate": prior,
            "prior_source": source,
            "seasonal_factor": seasonal,
            "observed_rate": observed,
            "alpha": alpha,
            "final_rate": final,
            "weekday_index": weekday_index,
            "safety_stock": levels["safety_stock"],
            "safety_method": levels["safety_method"],
            "min_stock": levels["min_stock"],
            "recommended_quantity": levels["recommended_quantity"],
            "max_stock": levels["max_stock"],
            "n_sales": n_sales,
            "confidence": confidence,
            "window_days": win["window_days"],
        }
