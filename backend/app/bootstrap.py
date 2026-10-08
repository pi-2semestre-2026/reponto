"""Boot sequence: create tables, seed categories, ingest dataset once, ensure model.

Idempotent and safe to run on every restart: ingestion is skipped when the
aggregate table is already populated and the model is loaded from its volume
instead of being retrained.
"""

import logging

from sqlalchemy import select

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.models import Category, CategoryPrior
from app.services.ml import rate_model
from app.services.seed_data import SEED_CATEGORIES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("bootstrap")


async def seed_categories() -> None:
    async with SessionLocal() as session:
        existing = {c.name: c for c in (await session.execute(select(Category))).scalars()}
        created = 0
        for spec in SEED_CATEGORIES:
            cat = existing.get(spec["name"])
            if cat is None:
                session.add(Category(name=spec["name"], description=spec["description"], keywords=spec["keywords"], is_seed=True))
                created += 1
            else:
                cat.description = spec["description"]
                cat.keywords = spec["keywords"]
        await session.commit()
        if created:
            logger.info("seeded %d categories", created)


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("tables ensured")


async def prepare_data() -> None:
    settings = get_settings()
    await create_tables()
    await seed_categories()

    from app.services.datasets import run_ingestion, sync_category_priors

    try:
        await run_ingestion()
    except Exception:
        logger.exception("dataset ingestion failed — continuing with default priors")

    try:
        await sync_category_priors()
    except Exception:
        logger.exception("category prior sync failed")

    from app.models import DatasetAggregate

    async with SessionLocal() as session:
        result = await session.execute(
            select(
                DatasetAggregate.month,
                DatasetAggregate.weekday,
                DatasetAggregate.size_bucket,
                DatasetAggregate.avg_sales_per_tx,
            )
        )
        rows = [
            {
                "month": r.month,
                "weekday": r.weekday,
                "size_bucket": r.size_bucket,
                "avg_sales_per_tx": r.avg_sales_per_tx,
            }
            for r in result
        ]
    rate_model.ensure(settings.ML_MODEL_PATH, rows)
    if not rate_model.ready:
        logger.warning("model unavailable — static category priors will be used")

    from app.services.categorizer import recover_stale_products

    try:
        recovered = await recover_stale_products()
        if recovered:
            logger.info("recovered %d stuck 'processing' product(s)", recovered)
    except Exception:
        logger.exception("stale product recovery failed")


async def main() -> None:
    await prepare_data()
    logger.info("bootstrap complete")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())