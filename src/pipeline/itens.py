"""Favorita POR ITEM (Kaggle "Grocery Sales Forecasting") -> vendas semanais loja x item.

`python -m pipeline.itens` lê data/raw/favorita_itens/train.csv (125 milhões de
linhas, 5 GB) em blocos e grava data/processed/favorita_itens_semanal.parquet
(regenerável, fora do git).

Diferenças em relação ao arquivo por família (data/raw/favorita):
  - Só existem linhas nos dias em que o item VENDEU. Dia sem linha = zero, mas
    só enquanto o item está "ativo" na loja (ver `active_weeks` em app_export_itens).
  - `unit_sales` negativo é devolução, não procura: vira zero antes de somar.
  - Itens vendidos por peso têm vendas fracionárias.
"""

import time

import numpy as np
import pandas as pd

from pipeline.config import PROCESSED_DIR, ROOT_DIR

RAW_ITEMS_DIR = ROOT_DIR / "data" / "raw" / "favorita_itens"
WEEKLY_ITEMS_FILE = PROCESSED_DIR / "favorita_itens_semanal.parquet"
FIRST_MONDAY = pd.Timestamp("2013-01-07")
N_WEEKS = 240  # semanas completas, seg-dom, de 2013-01-07 a 2017-08-13 (igual ao arquivo por família)
CHUNK_ROWS = 10_000_000


def load_items() -> pd.DataFrame:
    """item_nbr, family, class, perishable (0/1)."""
    return pd.read_csv(RAW_ITEMS_DIR / "items.csv")


def load_transactions() -> pd.DataFrame:
    """Cupons por loja e dia."""
    return pd.read_csv(RAW_ITEMS_DIR / "transactions.csv", parse_dates=["date"])


def weekly_from_chunks(path=None, chunk_rows: int = CHUNK_ROWS) -> pd.DataFrame:
    """Soma semanal por loja x item, lendo o CSV em blocos (memória limitada).

    Retorna store_nbr, item_nbr, week (0 = semana de 2013-01-07), sales.
    Só semanas completas; devoluções (venda negativa) viram zero.
    """
    path = path or RAW_ITEMS_DIR / "train.csv"
    parts = []
    started = time.perf_counter()
    reader = pd.read_csv(
        path,
        usecols=["date", "store_nbr", "item_nbr", "unit_sales"],
        dtype={"store_nbr": "int16", "item_nbr": "int32", "unit_sales": "float32"},
        chunksize=chunk_rows,
    )
    for i, chunk in enumerate(reader):
        dates = pd.to_datetime(pd.Series(chunk["date"].unique()))
        week_of = pd.Series(((dates - FIRST_MONDAY).dt.days // 7).to_numpy(), index=chunk["date"].unique())
        chunk["week"] = chunk["date"].map(week_of).astype("int16")
        chunk = chunk[(chunk["week"] >= 0) & (chunk["week"] < N_WEEKS)]
        chunk["unit_sales"] = chunk["unit_sales"].clip(lower=0)
        parts.append(chunk.groupby(["store_nbr", "item_nbr", "week"], sort=False)["unit_sales"].sum().reset_index())
        print(f"  bloco {i + 1}: {len(chunk):,} linhas ({time.perf_counter() - started:.0f}s)", flush=True)
    weekly = pd.concat(parts, ignore_index=True)
    # uma semana pode cair em dois blocos: soma de novo
    weekly = weekly.groupby(["store_nbr", "item_nbr", "week"], sort=True)["unit_sales"].sum().reset_index()
    return weekly.rename(columns={"unit_sales": "sales"}).astype({"sales": "float32"})


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    weekly = weekly_from_chunks()
    weekly.to_parquet(WEEKLY_ITEMS_FILE, index=False)
    n_series = weekly.groupby(["store_nbr", "item_nbr"]).ngroups
    print(f"\n{len(weekly):,} semanas com venda, {n_series:,} séries loja x item -> {WEEKLY_ITEMS_FILE}")
    print(f"semanas: {weekly['week'].min()}..{weekly['week'].max()} | venda semanal mediana: {np.median(weekly['sales']):.1f}")


if __name__ == "__main__":
    main()
