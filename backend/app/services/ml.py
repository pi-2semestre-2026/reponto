"""LightGBM seasonal demand model.

Trained once at boot from the aggregated Store Item Demand dataset
(features: month x weekday x store-size; target: mean units sold per item
per day) and persisted to a dedicated volume. On restarts the saved model
is loaded — retrained automatically only if the metadata version no longer
matches the current feature layout. Runtime prediction is a cached lookup.

The model is deliberately DATASET-WIDE (no product categories): the Kaggle
dataset carries no category information, so it only shapes the seasonal
pattern and store-size effect. The absolute level comes from the PT-BR
category baselines (app.services.seed_data).
"""

import json
import logging
import os

import lightgbm as lgb
import numpy as np

logger = logging.getLogger("ml")

META_SUFFIX = ".meta.json"
MODEL_VERSION = 2


class RateModel:
    def __init__(self) -> None:
        self.booster: lgb.Booster | None = None
        self.overall_mean: float | None = None
        self._cache: dict[tuple, float] = {}

    @property
    def ready(self) -> bool:
        return self.booster is not None and self.overall_mean is not None

    def _train(self, model_path: str, rows: list[dict]) -> None:
        rows = [r for r in rows if r.get("avg_sales_per_tx") is not None]
        if not rows:
            raise RuntimeError("no aggregated dataset rows to train on")

        X = np.array(
            [[r["month"], r["weekday"], r["size_bucket"]] for r in rows],
            dtype=np.float32,
        )
        y = np.array([r["avg_sales_per_tx"] for r in rows], dtype=np.float32)

        params = {
            "objective": "regression",
            "metric": "l2",
            "learning_rate": 0.06,
            "num_leaves": 31,
            "min_data_in_leaf": 10,
            "bagging_fraction": 0.9,
            "bagging_freq": 1,
            "feature_fraction": 0.9,
            "seed": 42,
            "verbose": -1,
        }
        dataset = lgb.Dataset(X, label=y)
        booster = lgb.train(params, dataset, num_boost_round=250)
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        booster.save_model(model_path)
        with open(model_path + META_SUFFIX, "w") as f:
            json.dump({"version": MODEL_VERSION, "overall_mean": float(y.mean())}, f)
        self.booster = booster
        self.overall_mean = float(y.mean())
        self._cache.clear()
        logger.info("LightGBM trained on %d rows (overall mean %.3f), saved to %s", len(rows), y.mean(), model_path)

    def _load(self, model_path: str) -> bool:
        meta_path = model_path + META_SUFFIX
        if not (os.path.exists(model_path) and os.path.exists(meta_path)):
            return False
        with open(meta_path) as f:
            meta = json.load(f)
        if meta.get("version") != MODEL_VERSION:
            logger.info("saved model meta version %r != %s — retraining", meta.get("version"), MODEL_VERSION)
            return False
        self.booster = lgb.Booster(model_file=model_path)
        self.overall_mean = meta.get("overall_mean")
        self._cache.clear()
        logger.info("LightGBM model loaded from %s", model_path)
        return True

    def ensure(self, model_path: str, rows: list[dict] | None = None) -> None:
        """Load saved model if present; otherwise train once and save.

        `rows` are the aggregated dataset rows (fetched by the caller); if
        not provided and no saved model exists, only static priors can be
        used.
        """
        try:
            if self._load(model_path):
                return
            if rows is None:
                logger.warning("no saved model and no rows provided — static priors will be used")
                return
            self._train(model_path, rows)
        except Exception:
            self.booster = None
            self.overall_mean = None
            logger.exception("model training/loading failed — falling back to static priors")

    def predict(self, month: int, weekday: int, size_bucket: int) -> float | None:
        """Mean units sold per item-day for the context. None when model unavailable."""
        if not self.ready:
            return None
        key = (month, weekday, size_bucket)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        pred = float(
            self.booster.predict(np.array([[month, weekday, size_bucket]], dtype=np.float32))[0]
        )
        pred = max(0.0, pred)
        self._cache[key] = pred
        return pred


rate_model = RateModel()
