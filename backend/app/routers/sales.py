import hashlib
import json
import datetime as dt
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from typing import Literal
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Market, Product, Sale, SaleItem
from app.routers.dep import get_current_user
from app.schemas import SaleCreateIn, SaleHistoryOut, SaleOut
from app.services.clock import day_bounds
from app.services.recommender import recalc_products

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
    idempotency_key: uuid.UUID | None = Header(default=None),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cart checkout: single transaction that decrements stock of every item.

    Blocked with a clear error if any item exceeds available stock.
    Retroactive sales (past sold_at) are accepted and respect the date.
    """
    request_hash = hashlib.sha256(json.dumps(payload.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
    if idempotency_key is not None:
        # Serialize concurrent retries before touching stock; committed retries reuse the receipt.
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                         {"key": f"checkout:{user.id}:{idempotency_key}"})
        existing = await db.scalar(select(Sale).where(Sale.user_id == user.id, Sale.idempotency_key == idempotency_key))
        if existing is not None:
            if existing.request_hash != request_hash:
                raise HTTPException(status_code=409, detail="Esta tentativa de venda já foi usada com outros itens")
            return await _load_sale(existing.id, db)

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
        idempotency_key=idempotency_key,
        request_hash=request_hash if idempotency_key else None,
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
                unit=product.unit,
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
    await recalc_products(product_ids, trigger)


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


@router.get("/history", response_model=SaleHistoryOut)
async def sale_history(
    market_id: uuid.UUID | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    product: str = Query(default="", max_length=160),
    quantity: Decimal | None = Query(default=None, gt=0, max_digits=12, decimal_places=3),
    order: Literal["recent", "value_desc", "value_asc", "quantity_desc", "quantity_asc"] = "recent",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=7, ge=1, le=100),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Sale).join(Market, Market.id == Sale.market_id).where(
        Market.owner_id == user.id,
    )
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="A data inicial deve ser anterior ou igual à data final")
    if market_id is not None:
        query = query.where(Sale.market_id == market_id)
    if date_from is not None:
        query = query.where(Sale.sold_at >= day_bounds(date_from, date_from)[0])
    if date_to is not None:
        query = query.where(Sale.sold_at < day_bounds(date_to, date_to)[1])
    # Match name and quantity on the same item, preserving multi-item receipts.
    if product.strip() or quantity is not None:
        item_match = select(SaleItem.id).where(SaleItem.sale_id == Sale.id)
        if product.strip():
            term = product.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            item_match = item_match.where(SaleItem.product_name.ilike(f"%{term}%", escape="\\"))
        if quantity is not None:
            item_match = item_match.where(SaleItem.quantity == quantity)
        query = query.where(item_match.exists())

    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    # Clamp pages after deletions or cancellations affecting filtered results.
    page = min(page, max(1, (total + page_size - 1) // page_size))
    if order.startswith("quantity_"):
        sort_value = select(func.coalesce(func.sum(SaleItem.quantity), 0)).where(SaleItem.sale_id == Sale.id).scalar_subquery()
    else:
        sort_value = Sale.total
    ordering = [] if order == "recent" else [sort_value.asc() if order.endswith("_asc") else sort_value.desc()]
    result = await db.execute(
        query.options(selectinload(Sale.items))
        .order_by(*ordering, Sale.sold_at.desc(), Sale.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    return SaleHistoryOut(items=[SaleOut.model_validate(sale) for sale in result.scalars()], total=total, page=page, page_size=page_size)


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
