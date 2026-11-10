"""Frente A — a limpeza extra dos dados de treino melhora o modelo?

Compara variantes SÓ no ano de validação (o ano de teste continua guardado), nas mesmas linhas:
  V0  como está (sem filtro de choque, sem promoção)
  V1  + semanas do terremoto fora do treino
  V2  + atributos de promoção (intensidade na semana e nas 8 anteriores)

Uso (raiz do repo): PYTHONPATH=backend DATASET_DIR=$PWD/datasets ML_MODEL_PATH=$PWD/backend/ml_data/model.txt \
    python scripts/experimentos/frente_a.py
"""

import logging

import numpy as np
import pandas as pd

logging.disable(logging.INFO)
from app.services import evaluation as ev  # noqa: E402
from app.services import weekly_model as wm  # noqa: E402

BASE = [f for f in wm.FEATURES if not f.startswith("promo")]
VARIANTS = {
    "V0 atual": (BASE, False),
    "V1 +sem terremoto": (BASE, True),
    "V2 +promoção bruta": (BASE + ["promo", "promo_hist"], True),
    "V3 +promoção sem escala": (BASE + ["promo_log", "promo_change"], True),
    "V4 +só mudança de promoção": (BASE + ["promo_change"], True),
}

weekly = ev.load_weekly()
feats = wm.add_features(weekly)
weeks = sorted(feats["week_start"].unique())
val = weeks[-(ev.TEST_WEEKS + ev.VALIDATION_WEEKS):-ev.TEST_WEEKS]

# Linhas de avaliação iguais para todos: alvo válido e fora das semanas do terremoto.
scored_all = feats[(feats["level"] > 0) & feats["sales"].notna() & (feats["shock"] == 0)]
scored_all = scored_all[scored_all["sales"] <= wm.MAX_TRAIN_RATIO * scored_all["level"]]
eval_rows = scored_all[scored_all["week_start"].isin(val)]


def wape(y, p):
    return 100 * np.abs(p - y).sum() / y.sum()


rows = []
for name, (features, drop_shock) in VARIANTS.items():
    wm.FEATURES[:] = features
    # wm.fit tira as semanas de choque sozinho; para a V0 a coluna é removida e elas entram no treino.
    train_pool = scored_all if drop_shock else feats[(feats["level"] > 0) & feats["sales"].notna() & (feats["sales"] <= wm.MAX_TRAIN_RATIO * feats["level"])].drop(columns="shock")
    preds = pd.Series(np.nan, index=eval_rows.index)
    origins = val[:: ev.REFIT_EVERY]
    for i, o in enumerate(origins):
        end = origins[i + 1] if i + 1 < len(origins) else None
        booster = wm.fit(train_pool[train_pool["week_start"] < o])
        m = (eval_rows["week_start"] >= o) & ((eval_rows["week_start"] < end) if end is not None else True)
        preds[m] = wm.predict(booster, eval_rows[m])
    r = eval_rows.assign(p=preds)
    tier = np.digitize(r["level"], wm.TIER_EDGES)
    small = r[tier <= 2]
    nopromo = r[r["promo"] == 0]
    rows.append({
        "variante": name,
        "WAPE geral": wape(r.sales, r.p),
        "<200 un/sem": wape(small.sales, small.p),
        "semanas sem promoção": wape(nopromo.sales, nopromo.p),
        "viés %": 100 * (r.p - r.sales).sum() / r.sales.sum(),
    })
    print(rows[-1], flush=True)

print("\nValidação (2015-08 a 2016-08), mesmas linhas para todas as variantes:")
print(pd.DataFrame(rows).set_index("variante").round(2).to_string())
