"""Fase 3 — perfil por dia da semana: qual método distribui melhor a semana pelos dias?

Para cada semana do ano de teste, a venda REAL da semana é distribuída pelos 7 dias
com o índice de cada método, calculado só com semanas anteriores (sem vazamento).
O erro diário (WAPE) mede apenas o mecanismo de dia da semana, isolado da previsão
do total semanal.

Métodos:
  plano        1/7 por dia
  geral        perfil médio de todas as séries (um para todo mundo)
  categoria    perfil médio da categoria do app
  cat×loja     categoria ajustada ao ritmo da loja (loja / geral)
  série(H,k)   perfil da própria série com peso decrescente (meia-vida H semanas),
               encolhido para cat×loja com k semanas de evidência a priori

Uso: python scripts/experimentos/perfil_dia_semana.py  (requer data/raw/favorita)
"""

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
from pipeline.app_export import FAMILY_TO_CATEGORY  # noqa: E402
from pipeline.data import load_train  # noqa: E402
from pipeline.weekly import week_start  # noqa: E402

TEST_WEEKS = 52
VAL_WEEKS = 52

d = load_train()
d["family"] = d["family"].astype(str)
d["week"] = week_start(d["date"])
d = d[(d["week"] >= "2013-01-07") & (d["week"] <= "2017-08-07")]
d["wd"] = d["date"].dt.weekday
born = d[d.sales > 0].groupby(["store_nbr", "family"]).week.min().rename("born")
d = d.merge(born, on=["store_nbr", "family"])
d = d[d.week >= d.born]
d["series"] = d.store_nbr.astype(str) + "|" + d.family
d["category"] = d.family.map(FAMILY_TO_CATEGORY)

# matrix: one row per series-week, 7 columns of daily sales (NaN where the day has no row: 25/12)
m = d.pivot_table(index=["series", "store_nbr", "category", "week"], columns="wd", values="sales", aggfunc="sum").reset_index()
days = list(range(7))
m["total"] = m[days].sum(axis=1)
m = m.sort_values(["series", "week"]).reset_index(drop=True)
full = m[days].notna().all(axis=1) & (m.total > 0)
share = m[days].div(m.total, axis=0) * 7  # index per weekday, mean 1 within the week
share[~full] = np.nan
weeks = sorted(m.week.unique())
test_weeks = weeks[-TEST_WEEKS:]
val_weeks = weeks[-(TEST_WEEKS + VAL_WEEKS):-TEST_WEEKS]
print(f"{m.series.nunique()} séries, {len(m):,} séries-semana")


def pooled(group_cols, upto):
    """Sales-weighted pooled index from weeks < upto (volume-weighted mean of shares)."""
    h = m[(m.week < upto) & full]
    s = h.groupby(group_cols)[days].sum()
    return s.div(s.sum(axis=1), axis=0) * 7


def evaluate(period):
    """Returns daily WAPE per method over `period` (prior pools refreshed every 13 weeks)."""
    rows = m[m.week.isin(period) & full].copy()
    preds = {}
    origins = period[::13]
    parts = {k: [] for k in ("geral", "categoria", "catloja")}
    for i, o in enumerate(origins):
        end = origins[i + 1] if i + 1 < len(origins) else pd.Timestamp("2100-01-01")
        r = rows[(rows.week >= o) & (rows.week < end)]
        g = pooled([], o) if False else None
        allp = m[(m.week < o) & full][days].sum()
        allp = allp / allp.sum() * 7
        cat = pooled(["category"], o)
        store = pooled(["store_nbr"], o)
        idx_g = np.tile(allp.values, (len(r), 1))
        idx_c = cat.reindex(r.category).values
        idx_s = store.reindex(r.store_nbr).values
        idx_cs = idx_c * idx_s / allp.values
        idx_cs = idx_cs / idx_cs.mean(axis=1, keepdims=True)
        for k, v in (("geral", idx_g), ("categoria", idx_c), ("catloja", idx_cs)):
            parts[k].append(pd.DataFrame(v, index=r.index, columns=days))
    for k in parts:
        preds[k] = pd.concat(parts[k]).loc[rows.index]
    preds["plano"] = pd.DataFrame(1.0, index=rows.index, columns=days)

    prior = preds["catloja"]
    for H in (4, 6, 8, 13, 26, None):
        r_ = 2 ** (-1 / H) if H else 1.0
        g = share.groupby(m.series)
        # exponentially-weighted sums over past full weeks (shift 1: only weeks before t)
        valid = share.notna().astype(float)
        def ew(x):
            return x.groupby(m.series).transform(lambda s: s.shift(1).fillna(0).ewm(alpha=1 - r_, adjust=False).mean() if H else s.shift(1).fillna(0).expanding().sum())
        num = ew(share.fillna(0))
        den = ew(valid)
        if H:
            # ewm(adjust=False) returns weighted means with weights summing to 1 - r^n; rescale to effective counts
            scale = 1 / (1 - r_)
            num, den = num * scale, den * scale
        own = (num / den.replace(0, np.nan)).loc[rows.index]
        n_eff = den.loc[rows.index]
        for k in (0.5, 1, 2, 4):
            est = (n_eff * own.fillna(0) + k * prior) / (n_eff + k)
            est = est.div(est.mean(axis=1), axis=0)
            preds[f"serie_H{H or 'inf'}_k{k}"] = est

    actual = rows[days]
    total = rows["total"].to_numpy()[:, None]
    out = {}
    for name, idx in preds.items():
        f = idx.to_numpy() * total / 7
        err = np.abs(f - actual.to_numpy())
        out[name] = 100 * np.nansum(err) / np.nansum(actual.to_numpy())
    return pd.Series(out).sort_values()


val = evaluate(val_weeks)
print("\n=== validação (escolha) ===")
print(val.round(2).head(12).to_string())
best = val.index[0]
test = evaluate(test_weeks)
print("\n=== teste ===")
print(test[[c for c in ["plano", "geral", "categoria", "catloja", best] if c in test.index]].round(2).to_string())
print(f"\nescolhido na validação: {best}; ganho no teste vs plano: {100 * (test['plano'] - test[best]) / test['plano']:.1f}%, vs geral: {100 * (test['geral'] - test[best]) / test['geral']:.1f}%")
