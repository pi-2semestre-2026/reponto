"""Production weekly demand model — validated in evaluation.py before it is used.

What it predicts: next week's units of ONE product in ONE store, from that
product's own weekly history (the store's own rhythm) plus what 1.729 real
supermarket series (Favorita, datasets/favorita/) taught about trend,
seasonality, category and holiday weeks.

Formulation (count data, any volume):
    level        = mean of the last 8 complete weeks (scale of the series)
    sales        ~ Tweedie(mu),  log(mu) = log(level) + f(features)
    f(features)  = LightGBM on scale-free features (lags / level, trend,
                   variability, share of zero weeks, week of year, category,
                   store size, national holidays in the week)
The offset log(level) makes the model scale-free: the same trees serve a
family that sells 60.000 units a week and a SKU that sells 3. The Tweedie
loss treats small counts as counts — a squared loss weighted by volume
ignored small series and lost to a 4-week moving average on them.

Uncertainty (split conformal): on a held-out year the ratio actual/forecast
is collected per volume tier; its 95th percentile q gives the upper bound
forecast x q. Calibrated on the validation year, that bound covered ~95% of
the weeks of the following test year in every tier (see /ml/evaluation).

Everything here is pure (no database, no app settings at import time), so the
recommender, the simulator brain and the backtest share the same code path.
"""

import datetime as dt
import json
import logging
import math
import os
import threading
from functools import lru_cache

import lightgbm as lgb
import numpy as np
import pandas as pd

logger = logging.getLogger("weekly_model")

MODEL_VERSION = 3
LEVEL_WEEKS = 8
MIN_WEEKS = 8
MAX_HISTORY_WEEKS = 60
NUM_ROUNDS = 400
TWEEDIE_POWER = 1.3
SERVICE_QUANTILE = 0.95
SERVICE_LEVELS = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)
MIN_TIER_ROWS = 300
# Training: weeks above MAX_TRAIN_RATIO x the recent level are one-off shocks no
# feature explains (they taught the trees absurd jumps). Production: the forecast
# is kept within [GUARD_LOW, GUARD_HIGH] x the product's recent level.
MAX_TRAIN_RATIO = 20.0
GUARD_LOW = 0.25
GUARD_HIGH = 4.0

TIER_EDGES = (5.0, 20.0, 200.0, 2000.0)
TIER_LABELS = ("<5", "5-20", "20-200", "200-2k", ">2k")

# Fixed codes: the position in this tuple is the categorical value the trees saw.
CATEGORIES = (
    "Bebidas",
    "Carnes e Aves",
    "Congelados e Frios",
    "Diversos",
    "Festa e Papelaria",
    "Higiene e Beleza",
    "Hortifrúti",
    "Lar e Cozinha",
    "Laticínios e Ovos",
    "Limpeza",
    "Mercearia",
    "Padaria",
    "Peixes e Frutos do Mar",
    "Pet e Bebê",
)

FEATURES = [
    "r_lag1", "r_lag2", "r_lag3", "r_lag4", "r_lag52",
    "r_ma4", "cv8", "trend", "zero8", "log_level",
    "weekofyear", "month", "size_bucket", "category", "holiday_days",
]
FEATURE_LABELS = {
    "r_lag1": "Venda da semana passada",
    "r_lag2": "Venda de 2 semanas atrás",
    "r_lag3": "Venda de 3 semanas atrás",
    "r_lag4": "Venda de 4 semanas atrás",
    "r_lag52": "Mesma semana do ano passado",
    "r_ma4": "Média das últimas 4 semanas",
    "cv8": "Variabilidade recente",
    "trend": "Tendência (4 sem. vs. 4 anteriores)",
    "zero8": "Semanas sem venda (últimas 8)",
    "log_level": "Volume do produto",
    "weekofyear": "Semana do ano",
    "month": "Mês",
    "size_bucket": "Porte da loja",
    "category": "Categoria",
    "holiday_days": "Feriados na semana",
}
PARAMS = {
    "objective": "tweedie",
    "tweedie_variance_power": TWEEDIE_POWER,
    "learning_rate": 0.05,
    "num_leaves": 63,
    "min_data_in_leaf": 100,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "lambda_l2": 1.0,
    "seed": 42,
    "deterministic": True,
    "verbose": -1,
}


# ---------------------------------------------------------------- calendar


def easter(year: int) -> dt.date:
    """Gregorian Easter Sunday (anonymous algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return dt.date(year, month, day)


@lru_cache(maxsize=64)
def br_national_holidays(year: int) -> frozenset:
    """National days off in Brazil (incl. Carnaval and Corpus Christi, widely observed)."""
    fixed = [(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (12, 25)]
    days = {dt.date(year, m, d) for m, d in fixed}
    if year >= 2024:
        days.add(dt.date(year, 11, 20))  # Consciência Negra, national since 2024
    e = easter(year)
    for offset in (-48, -47, -2, 60):  # Carnaval (seg, ter), Sexta-feira Santa, Corpus Christi
        days.add(e + dt.timedelta(days=offset))
    return frozenset(days)


def holiday_days_br(monday: dt.date) -> int:
    days = [monday + dt.timedelta(days=i) for i in range(7)]
    return sum(1 for d in days if d in br_national_holidays(d.year))


# ---------------------------------------------------------------- features


def category_code(name) -> float:
    return float(CATEGORIES.index(name)) if name in CATEGORIES else np.nan


def tier_of(level: float) -> str:
    return TIER_LABELS[int(np.digitize([level], TIER_EDGES)[0])]


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """Scale-free features for every row of a weekly panel.

    Input columns: series, week_start, sales, category (app name), size_bucket,
    holiday_days. Weeks of a series must be consecutive (zero-filled). Every
    feature of week t uses weeks <= t-1 only; holiday_days and the calendar of
    week t are known in advance. Rows keep their `sales` (NaN for the week to
    be forecast).
    """
    w = df.sort_values(["series", "week_start"]).reset_index(drop=True).copy()
    key = w["series"]
    g = w.groupby(key, sort=False)["sales"]
    for k in (1, 2, 3, 4, 52):
        w[f"lag{k}"] = g.shift(k)
    shifted = g.shift(1)
    sg = shifted.groupby(key, sort=False)
    w["level"] = sg.transform(lambda s: s.rolling(LEVEL_WEEKS).mean())
    w["ma4"] = sg.transform(lambda s: s.rolling(4).mean())
    w["std8"] = sg.transform(lambda s: s.rolling(LEVEL_WEEKS).std())
    zeros = (shifted == 0).astype(float).where(shifted.notna())
    w["zero8"] = zeros.groupby(key, sort=False).transform(lambda s: s.rolling(LEVEL_WEEKS).mean())
    w["ma4_prev"] = g.shift(5).groupby(key, sort=False).transform(lambda s: s.rolling(4).mean())

    level = w["level"].where(w["level"] > 0)
    for k in (1, 2, 3, 4, 52):
        w[f"r_lag{k}"] = w[f"lag{k}"] / level
    w["r_ma4"] = w["ma4"] / level
    w["cv8"] = w["std8"] / level
    w["trend"] = (w["ma4"] / w["ma4_prev"].where(w["ma4_prev"] > 0)).replace([np.inf, -np.inf], np.nan)
    w["log_level"] = np.log1p(w["level"])
    week = pd.to_datetime(w["week_start"])
    w["weekofyear"] = week.dt.isocalendar().week.astype(int).to_numpy()
    w["month"] = week.dt.month
    w["category"] = w["category"].map(category_code).astype(float)
    return w


def trainable(features: pd.DataFrame) -> pd.DataFrame:
    """Rows usable to fit or score: known level, known sales, not an extreme one-off shock."""
    ok = (features["level"] > 0) & features["sales"].notna()
    return features[ok & (features["sales"] <= MAX_TRAIN_RATIO * features["level"])]


def fit(rows: pd.DataFrame, num_rounds: int = NUM_ROUNDS) -> lgb.Booster:
    data = lgb.Dataset(
        rows[FEATURES],
        label=rows["sales"].to_numpy(),
        init_score=np.log(rows["level"].to_numpy()),
        categorical_feature=["category"],
    )
    return lgb.train(PARAMS, data, num_boost_round=num_rounds)


def predict(booster: lgb.Booster, rows: pd.DataFrame) -> np.ndarray:
    """Units for each row: level x exp(f(features))."""
    raw = booster.predict(rows[FEATURES], raw_score=True)
    return np.exp(raw) * rows["level"].to_numpy()


def conformal_quantiles(actual, forecast, level, q: float = SERVICE_QUANTILE) -> dict:
    """Multipliers per volume tier: percentiles of actual / forecast.

    "q" is the SERVICE_QUANTILE (95%) bound; "levels" holds every level in
    SERVICE_LEVELS, used by the newsvendor rule for perishables.
    """
    actual = np.asarray(actual, dtype=float)
    forecast = np.asarray(forecast, dtype=float)
    level = np.asarray(level, dtype=float)
    ok = forecast > 0
    ratio = actual[ok] / forecast[ok]
    tiers = np.digitize(level[ok], TIER_EDGES)
    overall = float(np.quantile(ratio, q)) if len(ratio) else 2.0
    out = {}
    for i, label in enumerate(TIER_LABELS):
        r = ratio[tiers == i]
        src = r if len(r) >= MIN_TIER_ROWS else ratio
        levels = {str(lv): round(float(np.quantile(src, lv)), 4) for lv in SERVICE_LEVELS} if len(src) else {}
        out[label] = {"q": round(float(np.quantile(src, q)), 4) if len(src) else 2.0, "levels": levels, "n": int(len(r))}
    # The multiplier must not grow with volume: larger series are relatively more predictable.
    for i in range(len(TIER_LABELS) - 2, -1, -1):
        hi, lo = out[TIER_LABELS[i + 1]], out[TIER_LABELS[i]]
        if lo["q"] < hi["q"]:
            lo["q"] = hi["q"]
        for lv in ("0.8", "0.9", "0.95"):
            if lv in lo["levels"] and lv in hi["levels"] and lo["levels"][lv] < hi["levels"][lv]:
                lo["levels"][lv] = hi["levels"][lv]
    out["overall"] = {
        "q": round(overall, 4),
        "levels": {str(lv): round(float(np.quantile(ratio, lv)), 4) for lv in SERVICE_LEVELS} if len(ratio) else {},
        "n": int(len(ratio)),
    }
    return out


# ---------------------------------------------------------------- history


def weekly_history(day_totals: dict, first_sale: dt.date, target_monday: dt.date, max_weeks: int = MAX_HISTORY_WEEKS) -> list[tuple[dt.date, float]]:
    """Complete Monday-Sunday weeks from the first full week after the first sale
    up to the week before `target_monday`, zero-filled (a week with no sale is demand 0)."""
    start = first_sale + dt.timedelta(days=(7 - first_sale.weekday()) % 7)
    start = max(start, target_monday - dt.timedelta(weeks=max_weeks))
    weeks = []
    monday = start
    while monday + dt.timedelta(days=7) <= target_monday:
        total = sum(float(day_totals.get(monday + dt.timedelta(days=i), 0.0)) for i in range(7))
        weeks.append((monday, total))
        monday += dt.timedelta(days=7)
    return weeks


# ---------------------------------------------------------------- production artifact


class WeeklyModel:
    def __init__(self) -> None:
        self.booster: lgb.Booster | None = None
        self.meta: dict = {}
        self._lock = threading.Lock()

    @staticmethod
    def paths() -> tuple[str, str]:
        from app.config import get_settings

        base = os.path.dirname(get_settings().ML_MODEL_PATH) or "."
        return os.path.join(base, "weekly_model.txt"), os.path.join(base, "weekly_model.meta.json")

    @property
    def ready(self) -> bool:
        return self.booster is not None and bool(self.meta.get("quantiles"))

    def load(self) -> bool:
        model_path, meta_path = self.paths()
        if not (os.path.exists(model_path) and os.path.exists(meta_path)):
            return False
        try:
            with open(meta_path, encoding="utf8") as f:
                meta = json.load(f)
            if meta.get("version") != MODEL_VERSION or meta.get("features") != FEATURES:
                logger.info("weekly model artifact is outdated (version %r) — waiting for retrain", meta.get("version"))
                return False
            booster = lgb.Booster(model_file=model_path)
        except Exception:
            logger.exception("could not load weekly model")
            return False
        with self._lock:
            self.booster, self.meta = booster, meta
        logger.info("weekly model loaded (%s rows, through %s)", meta.get("trained_rows"), meta.get("trained_through"))
        return True

    def save(self, booster: lgb.Booster, meta: dict) -> None:
        model_path, meta_path = self.paths()
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        booster.save_model(model_path)
        with open(meta_path, "w", encoding="utf8") as f:
            json.dump({**meta, "version": MODEL_VERSION, "features": FEATURES}, f, ensure_ascii=False)
        self.load()

    def tier_quantiles(self, tier: str) -> dict:
        q = self.meta.get("quantiles", {})
        return q.get(tier) or q.get("overall") or {"q": 2.0, "levels": {}}

    def quantile(self, tier: str) -> float:
        return float(self.tier_quantiles(tier)["q"])

    def forecast(self, weeks: list[tuple[dt.date, float]], target_monday: dt.date, category: str | None, size_bucket: int) -> dict | None:
        """Forecast for the week starting `target_monday`, or None when the model
        cannot be trusted for this product (not loaded, < MIN_WEEKS, no recent sales)."""
        if not self.ready or len(weeks) < MIN_WEEKS:
            return None
        rows = [{"week_start": w, "sales": float(q)} for w, q in weeks]
        rows.append({"week_start": target_monday, "sales": np.nan})
        df = pd.DataFrame(rows)
        df["series"] = 0
        df["category"] = category
        df["size_bucket"] = int(size_bucket)
        df["holiday_days"] = [holiday_days_br(pd.Timestamp(w).date()) for w in df["week_start"]]
        row = add_features(df).iloc[[-1]]
        level = float(row["level"].iloc[0])
        if not level > 0 or math.isnan(level):
            return None
        with self._lock:
            booster = self.booster
        raw = float(predict(booster, row)[0])
        weekly = min(max(raw, GUARD_LOW * level), GUARD_HIGH * level)
        tier = tier_of(level)
        q = self.quantile(tier)
        return {
            "weekly": weekly,
            "level": level,
            "tier": tier,
            "q95": q,
            "quantiles": self.tier_quantiles(tier).get("levels", {}),
            "upper": weekly * q,
            "weeks": len(weeks),
            "holiday_days": int(row["holiday_days"].iloc[0]),
            "has_last_year": not math.isnan(float(row["r_lag52"].iloc[0])),
            "guarded": weekly != raw,
        }


weekly_model = WeeklyModel()
