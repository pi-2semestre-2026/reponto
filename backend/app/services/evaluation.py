"""Walk-forward backtest: LightGBM vs. the "spreadsheet" baseline.

Answers the project's central question with numbers: does a machine-learning
forecaster beat a simple moving average on weekly demand?

Data: Store Item Demand (10 stores x 50 items, 2013-2017, daily sales)
aggregated to WEEKLY sales per store-item series (500 series x ~260 weeks).

Model: one GLOBAL LightGBM for all series, trained on scale-free features
(lags and rolling statistics divided by the series' recent level). The target
is next week's sales / level, so the same model applies to any product whose
weekly history is known, regardless of its volume.

Protocol (no leakage): expanding-window walk-forward over the last TEST_WEEKS
weeks, refitting every REFIT_EVERY weeks. Every forecast uses only weeks
strictly before it. Baselines are scored on the very same rows:
  - 4-week moving average (what a spreadsheet would do),
  - last week (naive),
  - same week last year (seasonal naive).
Metrics: MAE, MAPE, WAPE and bias.

Runs once (≈20-40 s) in a background thread and persists the result next to
the production model; the API only reads the JSON.
"""

import datetime as dt
import json
import logging
import os
import threading
import time

import lightgbm as lgb
import numpy as np
import pandas as pd

from app.config import get_settings

logger = logging.getLogger("evaluation")

EVAL_VERSION = 1
TEST_WEEKS = 26
REFIT_EVERY = 4
LEVEL_WEEKS = 8
NUM_ROUNDS = 300

FEATURES = [
    "r_lag1", "r_lag2", "r_lag3", "r_lag4", "r_lag52",
    "r_ma4", "cv8", "trend", "weekofyear", "month", "size_bucket",
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
    "weekofyear": "Semana do ano",
    "month": "Mês",
    "size_bucket": "Porte da loja",
}
MODEL_LABELS = {
    "lgbm": "LightGBM (Reponto)",
    "ma4": "Média móvel 4 semanas",
    "naive": "Repetir a semana passada",
    "snaive": "Mesma semana do ano passado",
}
PARAMS = {
    "objective": "regression",
    "metric": "l2",
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_data_in_leaf": 50,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "lambda_l2": 1.0,
    "seed": 42,
    "verbose": -1,
}

_state = {"status": "idle", "error": None, "started_at": None}
_lock = threading.Lock()


def _paths() -> tuple[str, str]:
    base = os.path.dirname(get_settings().ML_MODEL_PATH) or "."
    return os.path.join(base, "evaluation.json"), os.path.join(base, "weekly_model.txt")


# ---------------------------------------------------------------- data


def load_weekly() -> pd.DataFrame:
    from app.services.datasets import get_adapter

    root = get_adapter().locate()
    df = pd.read_csv(root / "train.csv", parse_dates=["date"], usecols=["date", "store", "item", "sales"])
    df["week"] = df["date"] - pd.to_timedelta(df["date"].dt.weekday, unit="D")
    days = df.groupby("week")["date"].nunique()
    full_weeks = days[days == 7].index
    w = (
        df[df["week"].isin(full_weeks)]
        .groupby(["store", "item", "week"], as_index=False)["sales"]
        .sum()
        .sort_values(["store", "item", "week"])
        .reset_index(drop=True)
    )
    volume = w.groupby("store")["sales"].sum()
    size = pd.qcut(volume.rank(method="first"), 4, labels=False).astype(int)
    w["size_bucket"] = w["store"].map(size)
    return w


def build_features(w: pd.DataFrame) -> pd.DataFrame:
    w = w.copy()
    g = w.groupby(["store", "item"], sort=False)["sales"]
    for k in (1, 2, 3, 4, 52):
        w[f"lag{k}"] = g.shift(k)
    shifted = g.shift(1)
    sg = shifted.groupby([w["store"], w["item"]], sort=False)
    w["level"] = sg.transform(lambda s: s.rolling(LEVEL_WEEKS).mean())
    w["ma4"] = sg.transform(lambda s: s.rolling(4).mean())
    w["std8"] = sg.transform(lambda s: s.rolling(LEVEL_WEEKS).std())
    w["ma4_prev"] = g.shift(5).groupby([w["store"], w["item"]], sort=False).transform(lambda s: s.rolling(4).mean())

    w = w[w["level"] > 0].copy()
    for k in (1, 2, 3, 4, 52):
        w[f"r_lag{k}"] = w[f"lag{k}"] / w["level"]
    w["r_ma4"] = w["ma4"] / w["level"]
    w["cv8"] = w["std8"] / w["level"]
    w["trend"] = w["ma4"] / w["ma4_prev"]
    w["weekofyear"] = w["week"].dt.isocalendar().week.astype(int)
    w["month"] = w["week"].dt.month
    w["ratio"] = w["sales"] / w["level"]
    return w.reset_index(drop=True)


# ---------------------------------------------------------------- metrics


def score(actual: np.ndarray, pred: np.ndarray) -> dict:
    actual = np.asarray(actual, dtype=float)
    pred = np.asarray(pred, dtype=float)
    mask = ~np.isnan(pred)
    actual, pred = actual[mask], pred[mask]
    err = pred - actual
    total = actual.sum()
    nonzero = actual > 0
    return {
        "mae": round(float(np.abs(err).mean()), 2),
        "mape": round(float((np.abs(err[nonzero]) / actual[nonzero]).mean() * 100), 2),
        "wape": round(float(np.abs(err).sum() / total * 100), 2) if total else None,
        "bias": round(float(err.sum() / total * 100), 2) if total else None,
        "n": int(mask.sum()),
    }


# ---------------------------------------------------------------- backtest


def run_backtest() -> dict:
    started = time.perf_counter()
    weekly = load_weekly()
    data = build_features(weekly)

    weeks = sorted(data["week"].unique())
    test_weeks = weeks[-TEST_WEEKS:]
    origins = test_weeks[::REFIT_EVERY]

    parts = []
    importance = np.zeros(len(FEATURES))
    final_model = None
    train_rows = 0
    for i, origin in enumerate(origins):
        end = origins[i + 1] if i + 1 < len(origins) else None
        train = data[data["week"] < origin]
        test = data[(data["week"] >= origin) & ((data["week"] < end) if end is not None else True)].copy()
        model = lgb.train(
            PARAMS,
            lgb.Dataset(train[FEATURES], label=train["ratio"], weight=train["level"]),
            num_boost_round=NUM_ROUNDS,
        )
        test["pred_lgbm"] = np.clip(model.predict(test[FEATURES]), 0, None) * test["level"]
        test["fold"] = i
        parts.append(test)
        importance += model.feature_importance(importance_type="gain")
        final_model = model
        train_rows = len(train)

    res = pd.concat(parts, ignore_index=True)
    res["pred_ma4"] = res["ma4"]
    res["pred_naive"] = res["lag1"]
    res["pred_snaive"] = res["lag52"]

    models = []
    for key in ("lgbm", "ma4", "naive", "snaive"):
        models.append({"key": key, "name": MODEL_LABELS[key], **score(res["sales"], res[f"pred_{key}"])})
    by_key = {m["key"]: m for m in models}
    lg, ma = by_key["lgbm"], by_key["ma4"]
    improvement = round((ma["wape"] - lg["wape"]) / ma["wape"] * 100, 1) if ma["wape"] else None

    folds = []
    for i, origin in enumerate(origins):
        f = res[res["fold"] == i]
        folds.append(
            {
                "fold": i + 1,
                "start": pd.Timestamp(origin).date().isoformat(),
                "weeks": int(f["week"].nunique()),
                "lgbm_wape": score(f["sales"], f["pred_lgbm"])["wape"],
                "ma4_wape": score(f["sales"], f["pred_ma4"])["wape"],
            }
        )

    weekly_total = (
        res.groupby("week")[["sales", "pred_lgbm", "pred_ma4"]].sum().reset_index().sort_values("week")
    )
    weekly_points = [
        {
            "week": pd.Timestamp(r.week).date().isoformat(),
            "actual": round(float(r.sales)),
            "lgbm": round(float(r.pred_lgbm)),
            "ma4": round(float(r.pred_ma4)),
        }
        for r in weekly_total.itertuples(index=False)
    ]

    per_series = (
        res.assign(
            e_l=(res["pred_lgbm"] - res["sales"]).abs(),
            e_m=(res["pred_ma4"] - res["sales"]).abs(),
        )
        .groupby(["store", "item"])[["e_l", "e_m", "sales"]]
        .sum()
    )
    win_rate = round(float((per_series["e_l"] < per_series["e_m"]).mean() * 100), 1)

    by_size = []
    for size, f in res.groupby("size_bucket"):
        by_size.append(
            {
                "size_bucket": int(size),
                "label": ["Pequena", "Média", "Grande", "Muito grande"][int(size)],
                "lgbm_wape": score(f["sales"], f["pred_lgbm"])["wape"],
                "ma4_wape": score(f["sales"], f["pred_ma4"])["wape"],
            }
        )

    samples = []
    volume = per_series["sales"].sort_values()
    for label, (store, item) in (
        ("Alto giro", volume.index[-1]),
        ("Giro médio", volume.index[len(volume) // 2]),
        ("Baixo giro", volume.index[0]),
    ):
        s = res[(res["store"] == store) & (res["item"] == item)].sort_values("week")
        hist = weekly[(weekly["store"] == store) & (weekly["item"] == item) & (weekly["week"] < test_weeks[0])].tail(12)
        points = [
            {"week": pd.Timestamp(r.week).date().isoformat(), "actual": int(r.sales), "lgbm": None, "ma4": None}
            for r in hist.itertuples(index=False)
        ] + [
            {
                "week": pd.Timestamp(r.week).date().isoformat(),
                "actual": int(r.sales),
                "lgbm": round(float(r.pred_lgbm), 1),
                "ma4": round(float(r.pred_ma4), 1),
            }
            for r in s.itertuples(index=False)
        ]
        sc_l = score(s["sales"], s["pred_lgbm"])
        sc_m = score(s["sales"], s["pred_ma4"])
        samples.append(
            {
                "label": f"{label} · loja {int(store)}, item {int(item)}",
                "lgbm_wape": sc_l["wape"],
                "ma4_wape": sc_m["wape"],
                "points": points,
            }
        )

    imp_total = importance.sum() or 1.0
    feature_importance = sorted(
        (
            {"feature": f, "label": FEATURE_LABELS[f], "pct": round(float(v / imp_total * 100), 1)}
            for f, v in zip(FEATURES, importance)
        ),
        key=lambda x: -x["pct"],
    )

    _, model_path = _paths()
    if final_model is not None:
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        final_model.save_model(model_path)

    return {
        "status": "ready",
        "version": EVAL_VERSION,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "elapsed_s": round(time.perf_counter() - started, 1),
        "dataset": {
            "name": "Store Item Demand Forecasting Challenge (Kaggle)",
            "stores": int(weekly["store"].nunique()),
            "items": int(weekly["item"].nunique()),
            "series": int(weekly.groupby(["store", "item"]).ngroups),
            "weeks": int(weekly["week"].nunique()),
            "first_week": pd.Timestamp(weekly["week"].min()).date().isoformat(),
            "last_week": pd.Timestamp(weekly["week"].max()).date().isoformat(),
        },
        "protocol": {
            "test_weeks": TEST_WEEKS,
            "refit_every": REFIT_EVERY,
            "folds": len(origins),
            "horizon": "1 semana à frente",
            "train_rows_last_fold": int(train_rows),
            "test_rows": int(len(res)),
            "features": len(FEATURES),
            "rounds": NUM_ROUNDS,
        },
        "models": models,
        "winner": min(models, key=lambda m: m["wape"])["key"],
        "improvement_vs_ma4_pct": improvement,
        "win_rate_vs_ma4_pct": win_rate,
        "folds": folds,
        "weekly_total": weekly_points,
        "by_size": by_size,
        "samples": samples,
        "feature_importance": feature_importance,
    }


# ---------------------------------------------------------------- persistence


def load_result() -> dict | None:
    path, _ = _paths()
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf8") as f:
            data = json.load(f)
        return data if data.get("version") == EVAL_VERSION else None
    except Exception:
        return None


def _run_and_save() -> None:
    path, _ = _paths()
    try:
        logger.info("backtest started (walk-forward, %d test weeks)", TEST_WEEKS)
        result = run_backtest()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf8") as f:
            json.dump(result, f, ensure_ascii=False)
        lg = next(m for m in result["models"] if m["key"] == "lgbm")
        ma = next(m for m in result["models"] if m["key"] == "ma4")
        logger.info(
            "backtest done in %.1fs: WAPE lgbm=%.2f%% ma4=%.2f%% (improvement %.1f%%)",
            result["elapsed_s"], lg["wape"], ma["wape"], result["improvement_vs_ma4_pct"] or 0,
        )
        _state.update(status="ready", error=None)
    except Exception as e:
        logger.exception("backtest failed")
        _state.update(status="error", error=str(e))


def start(force: bool = False) -> str:
    """Start the backtest in a daemon thread unless a valid result exists."""
    with _lock:
        if _state["status"] == "running":
            return "running"
        if not force and load_result() is not None:
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
