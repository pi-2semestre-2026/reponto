"""Frente B — treinar com dados POR ITEM melhora a previsão de produtos do tamanho de um SKU?

Avaliação sempre nas MESMAS séries loja x item, no ano de validação (o teste fica guardado),
mudando só o que o modelo viu no treino:
  A  famílias (modelo atual)      B  itens      C  famílias + itens
Referências nas mesmas linhas: média móvel de 4 semanas e a regra anterior do app (EMA).

Uso (raiz do repo):
  PYTHONPATH=backend DATASET_DIR=$PWD/datasets ML_MODEL_PATH=$PWD/backend/ml_data/model.txt \
    python scripts/experimentos/frente_b.py [validacao|teste]
"""

import logging
import sys

import numpy as np
import pandas as pd

logging.disable(logging.INFO)
from app.services import evaluation as ev  # noqa: E402
from app.services import weekly_model as wm  # noqa: E402

PERIOD = sys.argv[1] if len(sys.argv) > 1 else "validacao"

fam = wm.trainable(wm.add_features(ev.load_weekly("favorita")))
itm_all = wm.add_features(ev.load_weekly("favorita_itens"))
itm_all["ema"] = ev.ema_forecast(itm_all)
itm = wm.trainable(itm_all)

weeks = sorted(itm["week_start"].unique())
period = weeks[-ev.TEST_WEEKS:] if PERIOD == "teste" else weeks[-(ev.TEST_WEEKS + ev.VALIDATION_WEEKS):-ev.TEST_WEEKS]
rows = itm[itm["week_start"].isin(period)].dropna(subset=["ma4", "ema", "lag1"]).copy()
print(f"{PERIOD}: {pd.Timestamp(period[0]).date()} a {pd.Timestamp(period[-1]).date()} | "
      f"{len(rows):,} semanas de {rows['series'].nunique():,} séries loja x item | treino família {len(fam):,} / item {len(itm):,} linhas")

SOURCES = {"A família (atual)": [fam], "B item": [itm], "C família + item": [fam, itm]}
origins = period[:: ev.REFIT_EVERY]
for name, srcs in SOURCES.items():
    pool = pd.concat(srcs, ignore_index=True)
    pred = pd.Series(np.nan, index=rows.index)
    for i, o in enumerate(origins):
        end = origins[i + 1] if i + 1 < len(origins) else None
        booster = wm.fit(pool[pool["week_start"] < o])
        m = (rows["week_start"] >= o) & ((rows["week_start"] < end) if end is not None else True)
        pred[m] = wm.predict(booster, rows[m])
    rows[f"p_{name}"] = pred
    print("  treinado:", name, flush=True)
rows["p_média móvel 4"] = rows["ma4"]
rows["p_regra anterior (EMA)"] = rows["ema"]


def wape(d, c):
    return 100 * (d[c] - d["sales"]).abs().sum() / d["sales"].sum()


tiers = np.digitize(rows["level"], wm.TIER_EDGES)
labels = dict(enumerate(wm.TIER_LABELS))
out = {}
for c in [c for c in rows.columns if c.startswith("p_")]:
    r = {"WAPE geral": wape(rows, c), "viés %": 100 * (rows[c] - rows["sales"]).sum() / rows["sales"].sum()}
    for t in sorted(set(tiers)):
        r[labels[t]] = wape(rows[tiers == t], c)
    out[c[2:]] = r
table = pd.DataFrame(out).T
print("\nWAPE (%) por faixa de venda semanal (un/semana), mesmas linhas para todos:")
print(table.round(2).to_string())
print("\nlinhas por faixa:", {labels[t]: int((tiers == t).sum()) for t in sorted(set(tiers))})
