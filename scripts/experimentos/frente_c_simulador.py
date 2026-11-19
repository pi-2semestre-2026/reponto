"""Frente C, parte 2 — numa loja DIFERENTE das do treino, a margem geral acerta 95%?

As lojas do simulador seguem outra "realidade" (ruído lognormal + Poisson, eventos próprios).
Para cada partida: as previsões semanais do modelo para cada produto (só com o passado),
comparadas com a procura REAL da semana (não a venda, que é limitada pelo estoque).
  - cobertura com a margem geral (calibrada no Favorita);
  - cobertura com a margem ajustada à loja: fator f calculado nas semanas 9-30, aplicado nas 31-52.

Uso: PYTHONPATH=backend DATASET_DIR=$PWD/datasets ML_MODEL_PATH=$PWD/backend/ml_data/model.txt \
       python scripts/experimentos/frente_c_simulador.py
"""

import datetime as dt
import logging

import numpy as np
import pandas as pd

logging.disable(logging.INFO)
from app.config import get_settings  # noqa: E402
from app.services import weekly_model as wm  # noqa: E402
from app.services.ml import rate_model  # noqa: E402
from app.services.seed_data import size_bucket_from_customers  # noqa: E402
from simulator.engine import SimulationEngine  # noqa: E402

prof = pd.read_csv("datasets/favorita/perfil_diario.csv")
rate_model.ensure(get_settings().ML_MODEL_PATH, [
    {"family": r.category, "month": r.month, "weekday": r.weekday, "size_bucket": r.size_bucket, "avg_sales_per_tx": r.index}
    for r in prof.itertuples()
])
assert wm.weekly_model.load()
Q = {t: wm.weekly_model.quantile(t) for t in wm.TIER_LABELS}
K = 52
SPLIT = 30

rows = []
for scenario in ("bairro", "medio", "grande"):
    for seed in (11, 23, 37):
        e = SimulationEngine(scenario_key=scenario, days=364, cycle_days=7, seed=seed)
        while not e.done:
            e.step()
        start = e.start_date + dt.timedelta(days=(7 - e.start_date.weekday()) % 7)
        size = size_bucket_from_customers(e.customers_per_day)
        ev = pd.DataFrame(e.day_evals)
        ev["date"] = pd.to_datetime(ev["date"])
        for p in e.catalog:
            d = ev[ev["key"] == p["key"]].copy()
            d["week_start"] = d["date"] - pd.to_timedelta(d["date"].dt.weekday, unit="D")
            d = d[d["week_start"] >= pd.Timestamp(start)]
            w = d.groupby("week_start").agg(sales=("actual_sales", "sum"), demand=("actual_demand", "sum"), n=("date", "size"))
            w = w[w["n"] == 7].reset_index()
            w["series"], w["category"], w["size_bucket"] = 0, p["category"], size
            w["holiday_days"] = [wm.holiday_days_br(x.date()) for x in w["week_start"]]
            f = wm.add_features(w[["series", "week_start", "sales", "category", "size_bucket", "holiday_days"]])
            f["demand"] = w["demand"].to_numpy()
            f = f[f["level"] > 0]
            if f.empty:
                continue
            f["pred"] = np.clip(wm.predict(wm.weekly_model.booster, f), wm.GUARD_LOW * f["level"], wm.GUARD_HIGH * f["level"])
            f["tier"] = np.array(wm.TIER_LABELS)[np.digitize(f["level"], wm.TIER_EDGES)]
            f["week_no"] = np.arange(len(f)) + (len(w) - len(f))
            f["store"] = f"{scenario}-{seed}"
            rows.append(f[["store", "week_no", "tier", "pred", "demand", "sales"]])

r = pd.concat(rows, ignore_index=True)
r["q"] = r["tier"].map(Q)
r["z"] = (r["demand"] / r["pred"] - 1) / (r["q"] - 1)
fit, evl = r[r["week_no"] <= SPLIT], r[r["week_no"] > SPLIT]
g = fit.groupby("store")["z"]
f_store = ((g.size() * g.quantile(0.95).clip(0.5, 2.0) + K) / (g.size() + K)).clip(0.5, 2.0)
evl = evl.assign(f=evl["store"].map(f_store))
evl["q_store"] = 1 + (evl["q"] - 1) * evl["f"]
out = evl.groupby("store").apply(lambda x: pd.Series({
    "fator": x["f"].iloc[0],
    "cobertura geral %": (x["demand"] <= x["pred"] * x["q"]).mean() * 100,
    "cobertura ajustada %": (x["demand"] <= x["pred"] * x["q_store"]).mean() * 100,
    "margem geral (q)": x["q"].mean(),
    "margem ajustada (q)": x["q_store"].mean(),
}), include_groups=False)
print(out.round(2).to_string())
print("\nmédia:", out.mean().round(2).to_dict())
print("desvio médio da meta 95% (p.p.): geral", round((out["cobertura geral %"] - 95).abs().mean(), 2),
      "| ajustada", round((out["cobertura ajustada %"] - 95).abs().mean(), 2))
