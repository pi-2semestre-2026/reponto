"""Central dataset consumption — THE single file for external dataset intake.

The active dataset is the Kaggle "Store Item Demand Forecasting Challenge"
(datasets/Store Item Demand Forecasting Challenge/train.csv, columns
date/store/item/sales, 10 stores x 50 items, 5 years of daily data).

It has no product categories — what it gives us is the SALES RHYTHM of a
physical retail store: mean units sold per item per day by month x weekday
x store-size bucket. That aggregate (336 rows) is persisted once at boot;
the raw CSV is never read again at runtime.
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from sqlalchemy import delete, func, insert, select

from app.database import SessionLocal
from app.models import CategoryPrior, DatasetAggregate

logger = logging.getLogger("datasets")

FAMILY_NAME = "geral"


@dataclass
class AggregateRow:
    """One prior row: mean units per item-day for a context."""

    family: str
    month: int
    weekday: int
    size_bucket: int
    avg_sales_per_tx: float
    n_days: int


class StoreItemAdapter:
    """Kaggle Store Item Demand Forecasting Challenge adapter."""

    key = "store_item"
    label = "Store Item Demand Forecasting Challenge"
    required_files = ("train.csv",)

    def _store_size_buckets(self, df: pd.DataFrame) -> pd.Series:
        n_days = df["date"].nunique()
        volume = df.groupby("store")["sales"].sum() / n_days
        return pd.Series(
            pd.qcut(volume.rank(method="first"), 4, labels=False),
            index=volume.index,
            dtype="int64",
        )

    def aggregate(self) -> list[AggregateRow]:
        root = self.locate()
        df = pd.read_csv(root / "train.csv", parse_dates=["date"], usecols=["date", "store", "item", "sales"])
        if df.empty:
            raise RuntimeError("store_item: train.csv vazio")

        store_size = self._store_size_buckets(df)
        df["month"] = df["date"].dt.month
        df["weekday"] = df["date"].dt.weekday
        df["size"] = df["store"].map(store_size).astype(int)

        g = (
            df.groupby(["month", "weekday", "size"])
            .agg(total=("sales", "sum"), n_obs=("sales", "size"))
            .reset_index()
        )
        g["avg"] = g["total"] / g["n_obs"]
        dates_per_cell = df.groupby(["month", "weekday"])["date"].nunique()

        rows = [
            AggregateRow(
                family=FAMILY_NAME,
                month=int(r.month),
                weekday=int(r.weekday),
                size_bucket=int(r.size),
                avg_sales_per_tx=float(r.avg),
                n_days=int(dates_per_cell.loc[(r.month, r.weekday)]),
            )
            for r in g.itertuples(index=False)
        ]
        logger.info("store_item: %d aggregate rows from %d item-day observations", len(rows), len(df))
        return rows

    def find_root(self, base: Path) -> Path | None:
        """Find the folder holding this dataset's CSVs (base itself or any subdir)."""
        candidates = [base] + sorted(p for p in base.iterdir() if p.is_dir())
        for cand in candidates:
            if all((cand / f).exists() for f in self.required_files):
                return cand
        return None

    def locate(self) -> Path:
        base = Path(os.environ.get("DATASET_DIR", "/datasets"))
        root = self.find_root(base)
        if root is None:
            raise FileNotFoundError(
                f"dataset '{self.key}': arquivos {self.required_files} não encontrados em {base}"
            )
        return root


def get_adapter() -> StoreItemAdapter:
    return StoreItemAdapter()


async def run_ingestion() -> int:
    """Aggregate the dataset CSV and persist priors. Idempotent.

    Skips when this dataset's rows are already stored; wipes rows from any
    previously-active dataset first (raw CSVs are never read again at
    runtime). On failure the caller keeps working with default priors.
    """
    adapter = get_adapter()
    logger.info("dataset ativo: %s (%s)", adapter.key, adapter.label)

    async with SessionLocal() as session:
        ours = (
            await session.execute(
                select(func.count(DatasetAggregate.id)).where(DatasetAggregate.family == FAMILY_NAME)
            )
        ).scalar() or 0
        if ours > 0:
            logger.info("dataset já ingerido (%d linhas) — pulando leitura dos CSVs", ours)
            return ours

        rows = adapter.aggregate()
        total = (await session.execute(select(func.count(DatasetAggregate.id)))).scalar() or 0
        if total > 0:
            await session.execute(delete(DatasetAggregate))
            logger.info("removidas %d linhas de dataset anterior", total)

        await session.execute(
            insert(DatasetAggregate),
            [
                {
                    "family": r.family,
                    "category_id": None,
                    "month": r.month,
                    "weekday": r.weekday,
                    "size_bucket": r.size_bucket,
                    "avg_sales_per_tx": r.avg_sales_per_tx,
                    "n_days": r.n_days,
                }
                for r in rows
            ],
        )
        await session.commit()
        logger.info("dataset '%s' ingerido: %d linhas agregadas", adapter.key, len(rows))
        return len(rows)


async def sync_category_priors() -> None:
    """Keep CategoryPrior rows aligned with the calibrated baselines.

    Runs on EVERY boot (unlike run_ingestion): baselines live in code and
    evolve with product decisions. The dataset carries no categories, so
    static priors are pure code-level fallbacks used only when the ML model
    is unavailable.
    """
    from app.models import Category
    from app.services.seed_data import baseline_by_name

    async with SessionLocal() as session:
        categories = (await session.execute(select(Category))).scalars().all()
        for cat in categories:
            await session.merge(
                CategoryPrior(
                    category_id=cat.id,
                    prior_rate=baseline_by_name(cat.name),
                    n_days=0,
                )
            )
        await session.commit()
        logger.info("category priors sincronizados com baselines (%d categorias)", len(categories))
