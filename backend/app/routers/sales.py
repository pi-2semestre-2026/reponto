import datetime as dt
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import SessionLocal, get_db
from app.models import Market, Product, Sale, SaleItem
from app.routers.dep import get_current_user
from app.schemas import SaleCreateIn, SaleOut
from app.services.clock import day_bounds
from app.services.recommender import recalc_product

router = APIRouter(prefix="/sales", tags=["sales"])


def _ensure_utc(d: dt.datetime | None) -> dt.datetime | None:
    if d is None:
        return None
    if d.tzinfo is None:
        return d.replace(tzinfo=dt.timezone.utc)
    return d


async def _sale_owned(sale_id: uuid.UUID, user, db: AsyncSession) -> Sale:
    result = await db.execute(
        select(Sale)
        .join(Market, Market.id == Sale.market_id)
        .where(Sale.id == sale_id, Market.owner_id == user.id)
        .options(selectinload(Sale.items))
    )
    sale = result.scalar_one_or_none()
    if sale is None:
        raise HTTPException(status_code=404, detail="Venda não encontrada")
    return sale


@router.post("", response_model=SaleOut, status_code=201)
async def create_sale(
    payload: SaleCreateIn,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cart checkout: single transaction that decrements stock of every item.

    Blocked with a clear error if any item exceeds available stock.
    Retroactive sales (past sold_at) are accepted and respect the date.
    """
    market = await db.get(Market, payload.market_id)
    if market is None or market.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Mercado não encontrado")

    product_ids = list({item.product_id for item in payload.items})
    locked = await db.execute(
        select(Product)
        .where(Product.id.in_(product_ids), Product.market_id == market.id)
        .with_for_update()
    )
    products = {p.id: p for p in locked.scalars().all()}

    missing = [str(pid) for pid in product_ids if pid not in products]
    if missing:
        raise HTTPException(status_code=400, detail="Produto não encontrado neste mercado")

    sale = Sale(
        market_id=market.id,
        user_id=user.id,
        status="completed",
        sold_at=_ensure_utc(payload.sold_at) or dt.datetime.now(dt.timezone.utc),
    )
    total = Decimal("0")
    for item in payload.items:
        product = products[item.product_id]
        qty = item.quantity
        if qty > product.stock:
            raise HTTPException(
                status_code=400,
                detail=f"Estoque insuficiente para {product.name}: {product.stock.normalize()} disponível",
            )
        subtotal = (product.price * qty).quantize(Decimal("0.01"))
        product.stock = (product.stock - qty).quantize(Decimal("0.001"))
        total += subtotal
        sale.items.append(
            SaleItem(
                product_id=product.id,
                product_name=product.name,
                category_id=product.category_id,
                quantity=qty,
                unit_price=product.price,
                subtotal=subtotal,
            )
        )
    sale.total = total
    db.add(sale)
    await db.commit()
    await db.refresh(sale)

    await _recalc_products([i.product_id for i in sale.items])
    return await _load_sale(sale.id, db)


async def _recalc_products(product_ids: list[uuid.UUID | None], trigger: str = "sale") -> None:
    ids = [pid for pid in set(product_ids) if pid is not None]
    if not ids:
        return
    async with SessionLocal() as session:
        result = await session.execute(
            select(Product).where(Product.id.in_(ids)).options(selectinload(Product.category), selectinload(Product.market))
        )
        products = result.scalars().all()
        for p in products:
            await recalc_product(session, p, p.market, trigger)
        await session.commit()


async def _load_sale(sale_id: uuid.UUID, db: AsyncSession) -> Sale:
    result = await db.execute(
        select(Sale).where(Sale.id == sale_id).options(selectinload(Sale.items))
    )
    return result.scalar_one()


@router.get("", response_model=list[SaleOut])
async def list_sales(
    market_id: uuid.UUID | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Sale)
        .join(Market, Market.id == Sale.market_id)
        .where(Market.owner_id == user.id)
        .options(selectinload(Sale.items))
    )
    if market_id is not None:
        query = query.where(Sale.market_id == market_id)
    if date_from is not None:
        query = query.where(Sale.sold_at >= day_bounds(date_from, date_from)[0])
    if date_to is not None:
        query = query.where(Sale.sold_at < day_bounds(date_to, date_to)[1])
    query = query.order_by(Sale.sold_at.desc()).limit(500)
    return (await db.execute(query)).scalars().all()


@router.get("/{sale_id}", response_model=SaleOut)
async def get_sale(sale_id: uuid.UUID, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _sale_owned(sale_id, user, db)


@router.post("/{sale_id}/cancel", response_model=SaleOut)
async def cancel_sale(
    sale_id: uuid.UUID,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a sale: full restock and the sale stops influencing learning."""
    sale = await _sale_owned(sale_id, user, db)
    if sale.status == "cancelled":
        raise HTTPException(status_code=400, detail="Venda já está cancelada")

    item_ids = [i.product_id for i in sale.items if i.product_id is not None]
    locked = await db.execute(select(Product).where(Product.id.in_(item_ids)).with_for_update())
    products = {p.id: p for p in locked.scalars().all()}

    for item in sale.items:
        if item.product_id is not None and item.product_id in products:
            product = products[item.product_id]
            product.stock = (product.stock + item.quantity).quantize(Decimal("0.001"))

    sale.status = "cancelled"
    sale.cancelled_at = dt.datetime.now(dt.timezone.utc)
    await db.commit()

    await _recalc_products(item_ids, "sale_cancelled")
    return await _load_sale(sale.id, db)


@router.get("/stats/count")
async def sales_count(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(func.count(Sale.id)).join(Market, Market.id == Sale.market_id).where(Market.owner_id == user.id)
    )
    return {"count": result.scalar() or 0}