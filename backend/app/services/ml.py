"""LightGBM seasonal prior — the shape of demand BEFORE a product has history.

Trained once at boot from the dataset aggregate (app.services.datasets):
features month x weekday x store-size x category, target the seasonal index
of that context. With the Favorita profile the index is per APP CATEGORY
(Bebidas peaks differently from Limpeza); unknown categories (created by the
user or the LLM) use the `__all__` row. With the Store Item fallback there is
a single "geral" family. Persisted to the ml_data volume and reloaded on
restart; retrained when MODEL_VERSION or the set of families changes.

It only shapes SEASONALITY (month level and weekday shape, relative to the
category's own mean). The absolute level of a new product comes from the
category baselines (app.services.seed_data). Once a product has 8 complete
weeks of sales, the weekly model (app.services.weekly_model) takes over.
"""

import json
import logging
import os

import lightgbm as lgb
import numpy as np

logger = logging.getLogger("ml")

META_SUFFIX = ".meta.json"
MODEL_VERSION = 3
ALL_FAMILY = "__all__"


class RateModel:
    def __init__(self) -> None:
        self.booster: lgb.Booster | None = None
        self.overall_mean: float | None = None
        self.families: list[str] = []
        self._cache: dict[tuple, float] = {}
        self._means: dict[tuple, float] = {}

    @property
    def ready(self) -> bool:
        return self.booster is not None and self.overall_mean is not None

    def _clear(self) -> None:
        self._cache.clear()
        self._means.clear()

    def _train(self, model_path: str, rows: list[dict]) -> None:
        rows = [r for r in rows if r.get("avg_sales_per_tx") is not None]
        if not rows:
            raise RuntimeError("no aggregated dataset rows to train on")
        families = sorted({r.get("family") or "geral" for r in rows})
        code = {f: i for i, f in enumerate(families)}
        X = np.array(
            [[r["month"], r["weekday"], r["size_bucket"], code[r.get("family") or "geral"]] for r in rows],
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
        dataset = lgb.Dataset(X, label=y, categorical_feature=[3])
        booster = lgb.train(params, dataset, num_boost_round=250)
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        booster.save_model(model_path)
        with open(model_path + META_SUFFIX, "w") as f:
            json.dump({"version": MODEL_VERSION, "overall_mean": float(y.mean()), "families": families}, f, ensure_ascii=False)
        self.booster, self.overall_mean, self.families = booster, float(y.mean()), families
        self._clear()
        logger.info("seasonal LightGBM trained on %d rows, %d families, saved to %s", len(rows), len(families), model_path)

    def _load(self, model_path: str, families: list[str] | None) -> bool:
        meta_path = model_path + META_SUFFIX
        if not (os.path.exists(model_path) and os.path.exists(meta_path)):
            return False
        with open(meta_path) as f:
            meta = json.load(f)
        if meta.get("version") != MODEL_VERSION:
            logger.info("saved model meta version %r != %s — retraining", meta.get("version"), MODEL_VERSION)
            return False
        if families is not None and meta.get("families") != families:
            logger.info("dataset families changed — retraining the seasonal model")
            return False
        self.booster = lgb.Booster(model_file=model_path)
        self.overall_mean = meta.get("overall_mean")
        self.families = meta.get("families") or ["geral"]
        self._clear()
        logger.info("seasonal LightGBM loaded from %s (%d families)", model_path, len(self.families))
        return True

    def ensure(self, model_path: str, rows: list[dict] | None = None) -> None:
        """Load the saved model if it matches the dataset; otherwise train once and save."""
        try:
            families = sorted({r.get("family") or "geral" for r in rows}) if rows else None
            if self._load(model_path, families):
                return
            if not rows:
                logger.warning("no saved model and no rows provided — static priors will be used")
                return
            self._train(model_path, rows)
        except Exception:
            self.booster = None
            self.overall_mean = None
            logger.exception("model training/loading failed — falling back to static priors")

    def family_code(self, category: str | None) -> int:
        if category in self.families:
            return self.families.index(category)
        if ALL_FAMILY in self.families:
            return self.families.index(ALL_FAMILY)
        return 0

    def predict(self, month: int, weekday: int, size_bucket: int, category: str | None = None) -> float | None:
        """Seasonal index (or mean units per item-day on the fallback) for the context."""
        if not self.ready:
            return None
        key = (month, weekday, size_bucket, self.family_code(category))
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        pred = float(self.booster.predict(np.array([list(key)], dtype=np.float32))[0])
        pred = max(0.0, pred)
        self._cache[key] = pred
        return pred

    def reference_mean(self, size_bucket: int, category: str | None = None) -> float | None:
        """Mean prediction over the whole year for this category and store size (the 1.0 level)."""
        if not self.ready:
            return None
        key = (size_bucket, self.family_code(category))
        if key not in self._means:
            preds = [self.predict(m, w, size_bucket, category) for m in range(1, 13) for w in range(7)]
            self._means[key] = sum(preds) / len(preds)
        return self._means[key]


rate_model = RateModel()
