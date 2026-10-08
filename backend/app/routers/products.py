import datetime as dt
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Category, Product, RecommendationLog, StockAdjustment
from app.routers.dep import get_current_user, get_owned_market
from app.schemas import LearningLogOut, LearningPanelOut, ProductCreateIn, ProductOut, ProductUpdateIn, StockAdjustIn
from app.services.categorizer import process_product_background
from app.services.recommender import compute_blend, formula_string, recalc_product
from app.services.seed_data import DEFAULT_CATEGORY_NAME

router = APIRouter(tags=["products"])


async def _product_owned(product_id: uuid.UUID, user, db: AsyncSession) -> Product:
    result = await db.execute(
        select(Product)
        .where(Product.id == product_id)
        .options(selectinload(Product.category), selectinload(Product.market))
    )
    product = result.scalar_one_or_none()
    if product is None or product.market.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return product


@router.post("/markets/{market_id}/products", response_model=ProductOut, status_code=202)
async def create_product(
    market_id: uuid.UUID,
    payload: ProductCreateIn,
    background: BackgroundTasks,
    user=Depends(get_current_user),
    market=Depends(get_owned_market),
    db: AsyncSession = Depends(get_db),
):
    """Async creation: responds immediately with status=processing.

    Categorization (keywords -> LLM) + first recommendation run in background.
    """
    categories = (await db.execute(select(Category))).scalars().all()
    default = next((c for c in categories if c.name == DEFAULT_CATEGORY_NAME), None)
    if default is None and categories:
        default = categories[0]

    product = Product(
        market_id=market.id,
        category_id=default.id if default else None,
        name=payload.name.strip(),
        unit=payload.unit,
        price=payload.price,
        stock=payload.stock,
        status="processing",
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)

    background.add_task(process_product_background, product.id)
    return ProductOut(
        id=product.id,
        market_id=product.market_id,
        name=product.name,
        unit=product.unit,
        price=product.price,
        stock=product.stock,
        min_stock=product.min_stock,
        max_stock=product.max_stock,
        recommended_quantity=product.recommended_quantity,
        learned_rate=product.learned_rate,
        prior_rate=product.prior_rate,
        observed_rate=product.observed_rate,
        alpha=product.alpha,
        confidence=product.confidence,
        status=product.status,
        category_id=product.category_id,
        category_name=default.name if default else None,
        created_at=product.created_at,
    )


@router.get("/markets/{market_id}/products", response_model=list[ProductOut])
async def list_products(
    market=Depends(get_owned_market),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Product)
        .where(Product.market_id == market.id)
        .options(selectinload(Product.category))
        .order_by(Product.created_at.desc())
    )
    return result.scalars().all()


@router.patch("/products/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdateIn,
    background: BackgroundTasks,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    product = await _product_owned(product_id, user, db)
    if payload.name is not None:
        product.name = payload.name.strip()
    if payload.price is not None:
        product.price = payload.price
    if payload.unit is not None:
        product.unit = payload.unit
    await db.commit()
    await db.refresh(product)
    market = product.market
    await recalc_product(db, product, market, "product_updated")
    await db.commit()
    await db.refresh(product)
    return product


@router.delete("/products/{product_id}", status_code=204)
async def delete_product(
    product_id: uuid.UUID,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    product = await _product_owned(product_id, user, db)
    await db.delete(product)
    await db.commit()


@router.post("/products/{product_id}/stock", response_model=ProductOut)
async def adjust_stock(
    product_id: uuid.UUID,
    payload: StockAdjustIn,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    product = await _product_owned(product_id, user, db)
    new_stock = float(product.stock) + float(payload.delta)
    if new_stock < 0:
        raise HTTPException(status_code=400, detail="Estoque não pode ficar negativo")
    product.stock = round(new_stock, 3)
    db.add(StockAdjustment(product_id=product.id, delta=payload.delta, reason=payload.reason))
    market = product.market
    await recalc_product(db, product, market, "stock_adjust")
    await db.commit()
    await db.refresh(product)
    return product


@router.get("/products/{product_id}/learning", response_model=LearningPanelOut)
async def learning_panel(
    product_id: uuid.UUID,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    product = await _product_owned(product_id, user, db)
    market = product.market

    logs_result = await db.execute(
        select(RecommendationLog)
        .where(RecommendationLog.product_id == product.id)
        .order_by(RecommendationLog.created_at.desc(), RecommendationLog.id.desc())
        .limit(50)
    )
    logs = logs_result.scalars().all()

    blend = await compute_blend(db, product, market)

    evolution = [
        {
            "t": log.created_at.isoformat(),
            "final_rate": log.final_rate,
            "prior_rate": log.prior_rate,
            "observed_rate": log.observed_rate,
        }
        for log in reversed(logs)
    ]

    return LearningPanelOut(
        product_id=product.id,
        product_name=product.name,
        category_name=product.category_name,
        final_rate=blend["final_rate"],
        prior_rate=blend["prior_rate"],
        observed_rate=blend["observed_rate"],
        alpha=blend["alpha"],
        data_share_pct=round(blend["alpha"] * 100, 1),
        dataset_share_pct=round((1 - blend["alpha"]) * 100, 1),
        n_sales=blend["n_sales"],
        confidence=blend["confidence"],
        window_start=dt_utc(blend["window_start"]),
        window_end=dt_utc(blend["window_end"]),
        source=blend["prior_source"],
        min_stock=product.min_stock,
        max_stock=product.max_stock,
        recommended_quantity=product.recommended_quantity,
        formula=formula_string(blend),
        evolution=evolution,
        logs=[LearningLogOut.model_validate(log) for log in logs],
    )


def dt_utc(d):
    return dt.datetime.combine(d, dt.time.min)