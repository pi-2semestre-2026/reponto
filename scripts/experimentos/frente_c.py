"""Frente C — recalibrar a margem de 95% com o erro de cada loja ajuda?

Para cada loja, z = (vendido/previsto − 1) / (q95_da_faixa − 1): quanto do "meio-limite" geral o erro
daquela semana usou. O fator da loja é o percentil 95% de z (≈ 1 se a margem geral já serve para ela),
encolhido para 1 com k semanas de evidência a priori: f = (n·f_loja + k) / (n + k).
Margem da loja: q_loja = 1 + (q_faixa − 1) × f.

Escolha de k: no ano de VALIDAÇÃO, fator calculado no 1º semestre e cobertura medida no 2º.
Confirmação: fator calculado no ano de validação inteiro e cobertura medida no ano de TESTE.
O bom resultado é cobertura por loja mais perto de 95% (menos lojas descobertas ou com margem sobrando).

Uso: PYTHONPATH=backend DATASET_DIR=$PWD/datasets ML_MODEL_PATH=$PWD/backend/ml_data/model.txt \
       python scripts/experimentos/frente_c.py
"""

import logging

import numpy as np
import pandas as pd

logging.disable(logging.INFO)
from app.services import evaluation as ev  # noqa: E402
from app.services import weekly_model as wm  # noqa: E402

KS = (0, 13, 26, 52, 104, 208)
F_BOUNDS = (0.5, 2.0)

data = wm.trainable(wm.add_features(ev.load_weekly(ev.training_dataset())))
weeks = sorted(data["week_start"].unique())
val_period = weeks[-(ev.TEST_WEEKS + ev.VALIDATION_WEEKS):-ev.TEST_WEEKS]
test_period = weeks[-ev.TEST_WEEKS:]
val, _ = ev.walk_forward(data, val_period)
test, _ = ev.walk_forward(data, test_period)
for d in (val, test):
    d["tier"] = np.array(wm.TIER_LABELS)[np.digitize(d["level"], wm.TIER_EDGES)]


def tier_q(calib_rows):
    calib = wm.conformal_quantiles(calib_rows["sales"], calib_rows["pred_lgbm"], calib_rows["level"])
    return {t: calib[t]["q"] for t in wm.TIER_LABELS}


def z_of(rows, q):
    qt = rows["tier"].map(q)
    return (rows["sales"] / rows["pred_lgbm"] - 1) / (qt - 1)


def store_factors(rows, q, k):
    z = z_of(rows, q)
    g = pd.DataFrame({"store": rows["store_nbr"], "z": z}).groupby("store")["z"]
    raw = g.quantile(0.95).clip(*F_BOUNDS)
    n = g.size()
    return ((n * raw + k) / (n + k)).clip(*F_BOUNDS)


def evaluate(fit_rows, eval_rows, q):
    out = []
    for k in KS:
        f = store_factors(fit_rows, q, k) if k is not None else None
        fe = eval_rows["store_nbr"].map(f).fillna(1.0)
        q_store = 1 + (eval_rows["tier"].map(q) - 1) * fe
        cov = (eval_rows["sales"] <= eval_rows["pred_lgbm"] * q_store)
        by_store = cov.groupby(eval_rows["store_nbr"]).mean() * 100
        out.append({
            "k": k,
            "cobertura geral %": cov.mean() * 100,
            "desvio médio da meta (p.p.)": (by_store - 95).abs().mean(),
            "lojas entre 92% e 98%": int(((by_store >= 92) & (by_store <= 98)).sum()),
            "lojas abaixo de 90%": int((by_store < 90).sum()),
            "margem média (q)": float(q_store.mean()),
        })
    # referência: margem geral (fator 1 para todas)
    qg = eval_rows["tier"].map(q)
    cov = eval_rows["sales"] <= eval_rows["pred_lgbm"] * qg
    by_store = cov.groupby(eval_rows["store_nbr"]).mean() * 100
    out.insert(0, {"k": "geral (sem ajuste)", "cobertura geral %": cov.mean() * 100,
                   "desvio médio da meta (p.p.)": (by_store - 95).abs().mean(),
                   "lojas entre 92% e 98%": int(((by_store >= 92) & (by_store <= 98)).sum()),
                   "lojas abaixo de 90%": int((by_store < 90).sum()), "margem média (q)": float(qg.mean())})
    return pd.DataFrame(out).set_index("k").round(2)


half = val_period[len(val_period) // 2]
v1, v2 = val[val["week_start"] < half], val[val["week_start"] >= half]
print(f"lojas: {val['store_nbr'].nunique()} | semanas por loja no 1º semestre (mediana): {int(v1.groupby('store_nbr').size().median())}")
print("\n=== Escolha de k (validação: fator no 1º semestre, cobertura no 2º)")
print(evaluate(v1, v2, tier_q(v1)).to_string())
print("\n=== Confirmação (fator no ano de validação, cobertura no ano de teste)")
print(evaluate(val, test, tier_q(val)).to_string())
