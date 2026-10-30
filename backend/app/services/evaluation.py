"""Walk-forward backtest of the production weekly model, on real supermarket data.

Answers the project's central question with numbers: does the model that the
app actually uses beat what a spreadsheet would do — and the app's previous
rule — on weekly demand, and is its safety margin honest?

Data: Favorita (datasets/favorita/semanal.csv.gz) — 1.729 store x family
series of a real Ecuadorian chain, 240 weeks (2013-2017), every volume from a
few units to tens of thousands per week.

Protocol (no leakage, no tuning on the test set):
  - validation year (52 weeks) and test year (the last 52 weeks), both scored
    with an expanding-window walk-forward, refitting every REFIT_EVERY weeks;
    every forecast uses only weeks strictly before it;
  - the model design (Tweedie loss with log-level offset, features) was chosen
    on the validation year; the test year is reported untouched;
  - the 95% upper bound is calibrated on the validation year and its coverage
    is MEASURED on the test year (split conformal);
  - every baseline is scored on the very same rows:
        4-week moving average (the spreadsheet), the app's previous rule
        (exponential decay, half-life 30 days, 90-day window), last week,
        same week last year.
Metrics: MAE, MAPE, WAPE and bias, overall and per volume tier (a product of
a neighbourhood market sells < 200 units/week, so the small tiers matter most).

Finally the production model is refit on ALL weeks and saved, with conformal
multipliers recalibrated on the most recent held-out year. Runs once in a
background thread (~2-4 min) and persists the result; the API only reads it.
"""

import datetime as dt
import json
import logging
import os
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd

from app.config import get_settings
from app.services import weekly_model as wm

logger = logging.getLogger("evaluation")

EVAL_VERSION = 2
TEST_WEEKS = 52
VALIDATION_WEEKS = 52
REFIT_EVERY = 13
EMA_HALF_LIFE_DAYS = 30.0
EMA_WINDOW_WEEKS = 13

MODEL_LABELS = {
    "lgbm": "LightGBM (Reponto)",
    "ema": "Regra anterior do app (média com decaimento)",
    "ma4": "Média móvel 4 semanas",
    "naive": "Repetir a semana passada",
    "snaive": "Mesma semana do ano passado",
}
SIZE_LABELS = ["Pequena", "Média", "Grande", "Muito grande"]
TIER_NAMES = {
    "<5": "Menos de 5 un/semana",
    "5-20": "5 a 20 un/semana",
    "20-200": "20 a 200 un/semana",
    "200-2k": "200 a 2 mil un/semana",
    ">2k": "Mais de 2 mil un/semana",
}

_state = {"status": "idle", "error": None, "started_at": None}
_lock = threading.Lock()


def _result_path() -> str:
    base = os.path.dirname(get_settings().ML_MODEL_PATH) or "."
    return os.path.join(base, "evaluation.json")


# ---------------------------------------------------------------- data


def dataset_file() -> Path:
    return Path(get_settings().DATASET_DIR) / "favorita" / "semanal.csv.gz"


def load_weekly() -> pd.DataFrame:
    path = dataset_file()
    if not path.exists():
        raise FileNotFoundError(f"{path} não encontrado — gere com `python -m pipeline.app_export`")
    w = pd.read_csv(path, parse_dates=["week_start"])
    w["series"] = w["store_nbr"].astype(str) + "|" + w["family"]
    return w


def ema_forecast(data: pd.DataFrame) -> pd.Series:
    """The app's previous rule on weekly data: decay 2^(-age/half-life) over 13 weeks."""
    g = data.groupby("series", sort=False)["sales"]
    num = pd.Series(0.0, index=data.index)
    den = pd.Series(0.0, index=data.index)
    count = pd.Series(0, index=data.index)
    for age in range(EMA_WINDOW_WEEKS):
        weight = 2.0 ** (-7.0 * age / EMA_HALF_LIFE_DAYS)
        past = g.shift(1 + age)
        num += weight * past.fillna(0.0)
        den += weight * past.notna()
        count += past.notna().astype(int)
    return (num / den).where(count >= 4)


# ---------------------------------------------------------------- scoring


def score(actual, pred) -> dict:
    actual = np.asarray(actual, dtype=float)
    pred = np.asarray(pred, dtype=float)
    mask = ~np.isnan(pred)
    actual, pred = actual[mask], pred[mask]
    err = pred - actual
    total = actual.sum()
    nonzero = actual > 0
    return {
        "mae": round(float(np.abs(err).mean()), 2) if len(err) else None,
        "mape": round(float((np.abs(err[nonzero]) / actual[nonzero]).mean() * 100), 2) if nonzero.any() else None,
        "wape": round(float(np.abs(err).sum() / total * 100), 2) if total else None,
        "bias": round(float(err.sum() / total * 100), 2) if total else None,
        "n": int(mask.sum()),
    }


def walk_forward(data: pd.DataFrame, period: list) -> tuple[pd.DataFrame, list[dict]]:
    """Forecast every row of `period` with models refit every REFIT_EVERY weeks."""
    origins = period[::REFIT_EVERY]
    parts, folds = [], []
    for i, origin in enumerate(origins):
        end = origins[i + 1] if i + 1 < len(origins) else None
        train = data[data["week_start"] < origin]
        mask = (data["week_start"] >= origin) & ((data["week_start"] < end) if end is not None else data["week_start"].isin(period))
        test = data[mask].copy()
        booster = wm.fit(train)
        test["pred_lgbm"] = wm.predict(booster, test)
        test["fold"] = i
        parts.append(test)
        folds.append({"fold": i + 1, "start": pd.Timestamp(origin).date().isoformat(), "train_rows": int(len(train))})
        logger.info("fold %d/%d (%s): %d train rows", i + 1, len(origins), pd.Timestamp(origin).date(), len(train))
    return pd.concat(parts, ignore_index=True), folds


def with_baselines(res: pd.DataFrame) -> pd.DataFrame:
    res = res.assign(pred_ma4=res["ma4"], pred_naive=res["lag1"], pred_snaive=res["lag52"], pred_ema=res["ema"])
    keep = ["pred_lgbm", "pred_ma4", "pred_naive", "pred_snaive", "pred_ema"]
    return res.dropna(subset=keep).reset_index(drop=True)


def model_table(res: pd.DataFrame) -> list[dict]:
    return [{"key": k, "name": MODEL_LABELS[k], **score(res["sales"], res[f"pred_{k}"])} for k in MODEL_LABELS]


def wape_of(df: pd.DataFrame, key: str) -> float | None:
    return score(df["sales"], df[f"pred_{key}"])["wape"]


def gain(base: float | None, new: float | None) -> float | None:
    return round((base - new) / base * 100, 1) if base and new is not None else None


# ---------------------------------------------------------------- backtest


def run_backtest() -> dict:
    started = time.perf_counter()
    weekly = load_weekly()
    data = wm.add_features(weekly)
    data["ema"] = ema_forecast(data)
    data = wm.trainable(data)
    data["tier"] = np.array(wm.TIER_LABELS)[np.digitize(data["level"], wm.TIER_EDGES)]

    weeks = sorted(data["week_start"].unique())
    test_period = weeks[-TEST_WEEKS:]
    val_period = weeks[-(TEST_WEEKS + VALIDATION_WEEKS):-TEST_WEEKS]

    val_raw, _ = walk_forward(data, val_period)
    test_raw, test_folds = walk_forward(data, test_period)
    val, test = with_baselines(val_raw), with_baselines(test_raw)

    models = model_table(test)
    validation_models = model_table(val)
    by_key = {m["key"]: m for m in models}
    lg, ma, ema = by_key["lgbm"], by_key["ma4"], by_key["ema"]

    # Conformal: calibrate on validation, measure on test.
    calib = wm.conformal_quantiles(val["sales"], val["pred_lgbm"], val["level"])
    q_test = test["tier"].map(lambda t: calib[t]["q"])
    test["covered"] = test["sales"] <= test["pred_lgbm"] * q_test

    by_tier = []
    for label in wm.TIER_LABELS:
        f = test[test["tier"] == label]
        if f.empty:
            continue
        by_tier.append(
            {
                "tier": label,
                "label": TIER_NAMES[label],
                "rows": int(len(f)),
                "series": int(f["series"].nunique()),
                "lgbm_wape": wape_of(f, "lgbm"),
                "ma4_wape": wape_of(f, "ma4"),
                "ema_wape": wape_of(f, "ema"),
                "q95": calib[label]["q"],
                "coverage_pct": round(float(f["covered"].mean() * 100), 1),
            }
        )

    folds = []
    for i, meta in enumerate(test_folds):
        f = test[test["fold"] == i]
        folds.append({**meta, "weeks": int(f["week_start"].nunique()), "lgbm_wape": wape_of(f, "lgbm"), "ma4_wape": wape_of(f, "ma4"), "ema_wape": wape_of(f, "ema")})

    weekly_total = test.groupby("week_start")[["sales", "pred_lgbm", "pred_ma4", "pred_ema"]].sum().reset_index()
    weekly_points = [
        {"week": pd.Timestamp(r.week_start).date().isoformat(), "actual": round(float(r.sales)), "lgbm": round(float(r.pred_lgbm)), "ma4": round(float(r.pred_ma4)), "ema": round(float(r.pred_ema))}
        for r in weekly_total.itertuples(index=False)
    ]

    per_series = (
        test.assign(e_l=(test["pred_lgbm"] - test["sales"]).abs(), e_m=(test["pred_ma4"] - test["sales"]).abs())
        .groupby("series")[["e_l", "e_m", "sales", "level"]]
        .agg({"e_l": "sum", "e_m": "sum", "sales": "sum", "level": "mean"})
    )
    win_rate = round(float((per_series["e_l"] < per_series["e_m"]).mean() * 100), 1)

    by_size = [
        {"size_bucket": int(s), "label": SIZE_LABELS[int(s)], "lgbm_wape": wape_of(f, "lgbm"), "ma4_wape": wape_of(f, "ma4")}
        for s, f in test.groupby("size_bucket")
    ]
    by_category = sorted(
        (
            {"category": c, "series": int(f["series"].nunique()), "lgbm_wape": wape_of(f, "lgbm"), "ma4_wape": wape_of(f, "ma4"), "ema_wape": wape_of(f, "ema")}
            for c, f in test.assign(cat=test["series"].map(weekly.drop_duplicates("series").set_index("series")["category"])).groupby("cat")
        ),
        key=lambda x: x["category"],
    )

    samples = []
    tier_of_series = per_series["level"].map(wm.tier_of)
    for label, tier in (("Alto giro", ">2k"), ("Giro médio", "20-200"), ("Baixo giro", "5-20")):
        candidates = per_series[tier_of_series == tier].sort_values("sales")
        if candidates.empty:
            continue
        sid = candidates.index[len(candidates) // 2]
        s = test[test["series"] == sid].sort_values("week_start")
        hist = weekly[(weekly["series"] == sid) & (weekly["week_start"] < test_period[0])].tail(12)
        store, family = sid.split("|", 1)
        points = [{"week": pd.Timestamp(r.week_start).date().isoformat(), "actual": round(float(r.sales), 1), "lgbm": None, "ma4": None, "upper": None} for r in hist.itertuples(index=False)]
        points += [
            {
                "week": pd.Timestamp(r.week_start).date().isoformat(),
                "actual": round(float(r.sales), 1),
                "lgbm": round(float(r.pred_lgbm), 1),
                "ma4": round(float(r.pred_ma4), 1),
                "upper": round(float(r.pred_lgbm * calib[r.tier]["q"]), 1),
            }
            for r in s.itertuples(index=False)
        ]
        samples.append(
            {
                "label": f"{label} · loja {store}, {family.title()}",
                "lgbm_wape": wape_of(s, "lgbm"),
                "ma4_wape": wape_of(s, "ma4"),
                "coverage_pct": round(float(s["covered"].mean() * 100), 1),
                "points": points,
            }
        )

    # Production model: every known week; margins recalibrated on the latest held-out year.
    production = wm.fit(data)
    production_quantiles = wm.conformal_quantiles(test["sales"], test["pred_lgbm"], test["level"])
    trained_through = pd.Timestamp(data["week_start"].max()).date().isoformat()
    wm.weekly_model.save(
        production,
        {
            "trained_rows": int(len(data)),
            "trained_through": trained_through,
            "quantiles": production_quantiles,
            "service_quantile": wm.SERVICE_QUANTILE,
            "dataset": "Favorita (datasets/favorita/semanal.csv.gz)",
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        },
    )
    importance = production.feature_importance(importance_type="gain")
    imp_total = importance.sum() or 1.0
    feature_importance = sorted(
        ({"feature": f, "label": wm.FEATURE_LABELS[f], "pct": round(float(v / imp_total * 100), 1)} for f, v in zip(wm.FEATURES, importance)),
        key=lambda x: -x["pct"],
    )

    small = test[test["tier"].isin(["<5", "5-20", "20-200"])]
    return {
        "status": "ready",
        "version": EVAL_VERSION,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "elapsed_s": round(time.perf_counter() - started, 1),
        "dataset": {
            "name": "Favorita — Store Sales (Kaggle), rede de supermercados do Equador",
            "stores": int(weekly["store_nbr"].nunique()),
            "items": int(weekly["family"].nunique()),
            "series": int(weekly["series"].nunique()),
            "weeks": int(weekly["week_start"].nunique()),
            "first_week": pd.Timestamp(weekly["week_start"].min()).date().isoformat(),
            "last_week": pd.Timestamp(weekly["week_start"].max()).date().isoformat(),
        },
        "protocol": {
            "test_weeks": TEST_WEEKS,
            "validation_weeks": VALIDATION_WEEKS,
            "refit_every": REFIT_EVERY,
            "folds": len(test_folds),
            "horizon": "1 semana à frente",
            "validation_period": [pd.Timestamp(val_period[0]).date().isoformat(), pd.Timestamp(val_period[-1]).date().isoformat()],
            "test_period": [pd.Timestamp(test_period[0]).date().isoformat(), pd.Timestamp(test_period[-1]).date().isoformat()],
            "train_rows_last_fold": int(test_folds[-1]["train_rows"]),
            "test_rows": int(len(test)),
            "features": len(wm.FEATURES),
            "rounds": wm.NUM_ROUNDS,
            "loss": f"Tweedie (p={wm.TWEEDIE_POWER}) com offset log(nível)",
        },
        "models": models,
        "validation_models": validation_models,
        "winner": min(models, key=lambda m: m["wape"])["key"],
        "improvement_vs_ma4_pct": gain(ma["wape"], lg["wape"]),
        "improvement_vs_ema_pct": gain(ema["wape"], lg["wape"]),
        "improvement_small_vs_ma4_pct": gain(wape_of(small, "ma4"), wape_of(small, "lgbm")),
        "win_rate_vs_ma4_pct": win_rate,
        "calibration": {
            "target_pct": round(wm.SERVICE_QUANTILE * 100),
            "coverage_pct": round(float(test["covered"].mean() * 100), 1),
            "calibrated_on": "validação",
            "measured_on": "teste",
        },
        "folds": folds,
        "weekly_total": weekly_points,
        "by_size": by_size,
        "by_tier": by_tier,
        "by_category": by_category,
        "samples": samples,
        "feature_importance": feature_importance,
        "production": {
            "trained_rows": int(len(data)),
            "trained_through": trained_through,
            "quantiles": production_quantiles,
            "min_weeks": wm.MIN_WEEKS,
        },
    }


# ---------------------------------------------------------------- persistence


def load_result() -> dict | None:
    path = _result_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf8") as f:
            data = json.load(f)
        return data if data.get("version") == EVAL_VERSION else None
    except Exception:
        return None


def _run_and_save() -> None:
    path = _result_path()
    try:
        logger.info("backtest started (Favorita, validation %d + test %d weeks)", VALIDATION_WEEKS, TEST_WEEKS)
        result = run_backtest()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf8") as f:
            json.dump(result, f, ensure_ascii=False)
        lg = next(m for m in result["models"] if m["key"] == "lgbm")
        ma = next(m for m in result["models"] if m["key"] == "ma4")
        logger.info(
            "backtest done in %.1fs: WAPE lgbm=%.2f%% ma4=%.2f%% (−%.1f%%), coverage %.1f%%",
            result["elapsed_s"], lg["wape"], ma["wape"], result["improvement_vs_ma4_pct"] or 0, result["calibration"]["coverage_pct"],
        )
        _state.update(status="ready", error=None)
    except Exception as e:
        logger.exception("backtest failed")
        _state.update(status="error", error=str(e))


def start(force: bool = False) -> str:
    """Start the backtest in a daemon thread unless a valid result and model exist."""
    with _lock:
        if _state["status"] == "running":
            return "running"
        if not force and load_result() is not None and (wm.weekly_model.ready or wm.weekly_model.load()):
            _state["status"] = "ready"
            return "ready"
        _state.update(status="running", error=None, started_at=time.time())
    threading.Thread(target=_run_and_save, name="backtest", daemon=True).start()
    return "running"


def status() -> dict:
    result = load_result()
    if result is not None and _state["status"] != "running":
        return result
    out = {"status": _state["status"], "error": _state["error"]}
    if _state["started_at"]:
        out["running_for_s"] = round(time.time() - _state["started_at"])
    return out
