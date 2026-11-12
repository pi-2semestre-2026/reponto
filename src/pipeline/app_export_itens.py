"""Recorte do Favorita POR ITEM para o app: `python -m pipeline.app_export_itens`.

Lê data/processed/favorita_itens_semanal.parquet (gerado por `python -m pipeline.itens`)
e grava datasets/favorita_itens/semanal.csv.gz no MESMO formato do recorte por família
(datasets/favorita/), mais `item_nbr` e `perishable`. O backend usa o mesmo carregador.

Regras de qualidade (decididas antes de olhar qualquer erro de previsão):
  1. Ativo na loja: do primeiro ao último mês com venda. Dentro disso, semana sem
     linha = zero (o arquivo do Kaggle só tem linhas de dias com venda).
  2. Fora da prateleira: uma sequência de semanas zeradas longa demais para o ritmo
     do item (GAP_WEEKS_FAST para quem vende >= FAST_MEDIAN/semana, GAP_WEEKS_SLOW
     para os lentos) é item fora de linha ou em falta, não procura zero: a série é
     cortada ali (`segment`), como os apagões do recorte por família.
  3. Amostra estratificada por volume, com mais séries no regime de mercadinho
     (< 200 un/semana); semente fixa, resultado reproduzível.
"""

import numpy as np
import pandas as pd

from pipeline.app_export import FAMILY_TO_CATEGORY, SHOCK_WEEKS, national_holidays
from pipeline.config import ROOT_DIR
from pipeline.data import load_holidays
from pipeline.itens import FIRST_MONDAY, WEEKLY_ITEMS_FILE, load_items

EXPORT_DIR = ROOT_DIR / "datasets" / "favorita_itens"
MIN_ACTIVE_WEEKS = 40
FAST_MEDIAN = 3.0
GAP_WEEKS_FAST = 4
GAP_WEEKS_SLOW = 12
SEED = 2026
# séries por faixa de venda semanal mediana (un/semana)
TIER_EDGES = (5.0, 20.0, 200.0)
TIER_TARGET = {0: 1000, 1: 1400, 2: 1200, 3: 400}


def series_summary(weekly: pd.DataFrame) -> pd.DataFrame:
    g = weekly[weekly["sales"] > 0].groupby(["store_nbr", "item_nbr"])
    s = g["week"].agg(first="min", last="max").reset_index()
    s["span"] = s["last"] - s["first"] + 1
    med = weekly[weekly["sales"] > 0].groupby(["store_nbr", "item_nbr"])["sales"].median().rename("median_nonzero")
    return s.merge(med.reset_index(), on=["store_nbr", "item_nbr"])


def sample_series(summary: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    eligible = summary[summary["span"] >= MIN_ACTIVE_WEEKS].copy()
    eligible["tier"] = np.digitize(eligible["median_nonzero"], TIER_EDGES)
    picked = []
    for tier, n in TIER_TARGET.items():
        pool = eligible[eligible["tier"] == tier]
        take = min(n, len(pool))
        picked.append(pool.iloc[rng.choice(len(pool), size=take, replace=False)])
    return pd.concat(picked, ignore_index=True)


def densify_and_split(weekly: pd.DataFrame, chosen: pd.DataFrame) -> pd.DataFrame:
    """Zeros dentro do período ativo; corte em sequências de zeros longas (fora da prateleira)."""
    w = weekly.merge(chosen[["store_nbr", "item_nbr", "first", "last", "median_nonzero"]], on=["store_nbr", "item_nbr"])
    out = []
    for (store, item), s in w.groupby(["store_nbr", "item_nbr"], sort=False):
        first, last, med = int(s["first"].iloc[0]), int(s["last"].iloc[0]), float(s["median_nonzero"].iloc[0])
        s = s[(s["week"] >= first) & (s["week"] <= last)]  # semanas zeradas por devolução fora do período ativo
        full = pd.Series(0.0, index=np.arange(first, last + 1))
        full.loc[s["week"].to_numpy()] = s["sales"].to_numpy()
        zero = (full.to_numpy() == 0)
        run_id = np.cumsum(np.r_[True, zero[1:] != zero[:-1]])
        run_len = pd.Series(zero).groupby(run_id).transform("sum").to_numpy()
        limit = GAP_WEEKS_FAST if med >= FAST_MEDIAN else GAP_WEEKS_SLOW
        gap = zero & (run_len >= limit)
        segment = np.cumsum(gap)
        keep = ~gap
        out.append(pd.DataFrame({
            "store_nbr": store,
            "item_nbr": item,
            "week": full.index[keep],
            "sales": full.to_numpy()[keep],
            "segment": segment[keep],
        }))
    res = pd.concat(out, ignore_index=True)
    res["segment"] = res.groupby(["store_nbr", "item_nbr"])["segment"].rank(method="dense").astype(int) - 1
    return res


def main() -> None:
    weekly = pd.read_parquet(WEEKLY_ITEMS_FILE)
    items = load_items()
    rng = np.random.default_rng(SEED)

    summary = series_summary(weekly)
    chosen = sample_series(summary, rng)
    dense = densify_and_split(weekly, chosen)

    dense = dense.merge(items[["item_nbr", "family", "perishable"]], on="item_nbr", how="left")
    dense["category"] = dense["family"].map(FAMILY_TO_CATEGORY)
    volume = weekly.groupby("store_nbr")["sales"].sum()
    sizes = pd.Series(pd.qcut(volume.rank(method="first"), 4, labels=False), index=volume.index).astype(int)
    dense["size_bucket"] = dense["store_nbr"].map(sizes).astype(int)
    dense["week_start"] = FIRST_MONDAY + pd.to_timedelta(dense["week"] * 7, unit="D")
    hol = national_holidays(load_holidays())
    per_week = (hol - pd.to_timedelta(hol.dt.weekday, unit="D")).value_counts()
    dense["holiday_days"] = dense["week_start"].map(per_week).fillna(0).astype(int)
    dense["shock"] = dense["week_start"].between(*SHOCK_WEEKS).astype(int)
    dense["sales"] = dense["sales"].round(3)

    cols = ["store_nbr", "item_nbr", "family", "perishable", "segment", "category", "size_bucket", "week_start", "sales", "holiday_days", "shock"]
    dense = dense[cols].sort_values(["store_nbr", "item_nbr", "week_start"]).reset_index(drop=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = EXPORT_DIR / "semanal.csv.gz"
    dense.to_csv(out, index=False, compression={"method": "gzip", "mtime": 0})

    tiers = np.digitize(chosen["median_nonzero"], TIER_EDGES)
    print(f"elegíveis: {int((summary['span'] >= MIN_ACTIVE_WEEKS).sum()):,} de {len(summary):,} séries loja x item")
    print("amostra por faixa:", dict(zip(*np.unique(tiers, return_counts=True))))
    print(f"{len(dense):,} semanas, {dense.groupby(['store_nbr', 'item_nbr']).ngroups} séries "
          f"({dense.groupby(['store_nbr', 'item_nbr', 'segment']).ngroups} trechos), "
          f"{dense['category'].nunique()} categorias, {dense['perishable'].mean():.0%} das semanas de itens perecíveis")
    print(f"zeros: {(dense['sales'] == 0).mean():.1%} das semanas | arquivo {out.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
