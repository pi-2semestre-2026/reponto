import datetime as dt
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, bindparam, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Category, Market, Product, Sale, SaleItem
from app.services.clock import LOCAL_TZ_NAME, day_bounds, today_local
from app.routers.dep import get_current_user
from app.schemas import (
    AnalyticsOut,
    CategoryRevenueOut,
    DailyPointOut,
    LowStockAlert,
    MarketOverview,
    PeriodStats,
    TopProductOut,
)

router = APIRouter(tags=["analytics"])


def _bounds(date_from: dt.date, date_to: dt.date) -> tuple[dt.datetime, dt.datetime]:
    return day_bounds(date_from, date_to)


def _pct_change(current: Decimal, previous: Decimal) -> float | None:
    prev = float(previous)
    if prev <= 0:
        return None
    return round((float(current) - prev) / prev * 100, 1)


async def _period_stats(db, owner_id, start: dt.datetime, end: dt.datetime, market_id: uuid.UUID | None) -> PeriodStats:
    criteria = [
        Market.owner_id == owner_id,
        Sale.status == "completed",
        Sale.sold_at >= start,
        Sale.sold_at < end,
    ]
    if market_id is not None:
        criteria.append(Sale.market_id == market_id)

    sales_row = (
        await db.execute(
            select(func.count(Sale.id), func.coalesce(func.sum(Sale.total), 0))
            .join(Market, Market.id == Sale.market_id)
            .where(*criteria)
        )
    ).one()
    sales_count = int(sales_row[0])
    revenue = Decimal(sales_row[1] or 0)

    items_row = (
        await db.execute(
            select(func.coalesce(func.sum(SaleItem.quantity), 0))
            .join(Sale, Sale.id == SaleItem.sale_id)
            .join(Market, Market.id == Sale.market_id)
            .where(*criteria)
        )
    ).one()
    items_sold = Decimal(items_row[0] or 0)
    avg_ticket = (revenue / sales_count).quantize(Decimal("0.01")) if sales_count else Decimal("0")
    return PeriodStats(revenue=revenue, sales_count=sales_count, items_sold=items_sold, avg_ticket=avg_ticket)


@router.get("/analytics", response_model=AnalyticsOut)
async def analytics(
    date_from: dt.date | None = Query(default=None),
    date_to: dt.date | None = Query(default=None),
    market_id: uuid.UUID | None = Query(default=None),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    today = today_local()
    date_to = date_to or today
    date_from = date_from or (date_to - dt.timedelta(days=29))
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="Data inicial não pode ser maior que a final")

    if market_id is not None:
        market = await db.get(Market, market_id)
        if market is None or market.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Mercado não encontrado")

    start, end = _bounds(date_from, date_to)
    period_days = (date_to - date_from).days + 1
    prev_to = date_from - dt.timedelta(days=1)
    prev_from = date_from - dt.timedelta(days=period_days)
    prev_start, prev_end = _bounds(prev_from, prev_to)

    stats = await _period_stats(db, user.id, start, end, market_id)
    previous = await _period_stats(db, user.id, prev_start, prev_end, market_id)

    status_filter = Sale.status == "completed"
    scope = [Market.owner_id == user.id, status_filter, Sale.sold_at >= start, Sale.sold_at < end]
    if market_id is not None:
        scope.append(Sale.market_id == market_id)

    top_rows = (
        await db.execute(
            select(SaleItem.product_name, SaleItem.category_id, func.sum(SaleItem.quantity), func.sum(SaleItem.subtotal))
            .join(Sale, Sale.id == SaleItem.sale_id)
            .join(Market, Market.id == Sale.market_id)
            .where(*scope)
            .group_by(SaleItem.product_name, SaleItem.category_id)
            .order_by(func.sum(SaleItem.subtotal).desc())
            .limit(8)
        )
    ).all()

    cat_rows = (
        await db.execute(
            select(SaleItem.category_id, func.sum(SaleItem.subtotal), func.sum(SaleItem.quantity))
            .join(Sale, Sale.id == SaleItem.sale_id)
            .join(Market, Market.id == Sale.market_id)
            .where(*scope)
            .group_by(SaleItem.category_id)
            .order_by(func.sum(SaleItem.subtotal).desc())
        )
    ).all()

    app_tz = bindparam("app_tz", LOCAL_TZ_NAME, literal_execute=True)
    daily_rows = (
        await db.execute(
            select(
                func.date(func.timezone(app_tz, Sale.sold_at)).label("day"),
                func.count(Sale.id),
                func.sum(Sale.total),
            )
            .join(Market, Market.id == Sale.market_id)
            .where(*scope)
            .group_by("day")
            .order_by("day")
        )
    ).all()

    categories = {c.id: c.name for c in (await db.execute(select(Category))).scalars()}

    top_products = [
        TopProductOut(
            product_name=name,
            category_name=categories.get(cid) if cid else None,
            quantity=Decimal(qty or 0),
            revenue=Decimal(rev or 0),
        )
        for name, cid, qty, rev in top_rows
    ]
    revenue_by_category = [
        CategoryRevenueOut(
            category_name=categories.get(cid) if cid else "Sem categoria",
            revenue=Decimal(rev or 0),
            quantity=Decimal(qty or 0),
        )
        for cid, rev, qty in cat_rows
    ]
    daily_series = [
        DailyPointOut(date=d if isinstance(d, dt.date) else dt.date.fromisoformat(str(d)), revenue=Decimal(rev or 0), sales_count=int(cnt))
        for d, cnt, rev in daily_rows
    ]

    stock_rows = (
        await db.execute(
            select(Category.name, func.coalesce(func.sum(Product.stock), 0), func.coalesce(func.sum(Product.stock * Product.price), 0))
            .join(Market, Market.id == Product.market_id)
            .outerjoin(Category, Category.id == Product.category_id)
            .where(Market.owner_id == user.id, *([Market.id == market_id] if market_id is not None else []))
            .group_by(Category.name)
        )
    ).all()
    stock_by_category = [
        CategoryRevenueOut(category_name=name or "Sem categoria", revenue=Decimal(rev or 0), quantity=Decimal(qty or 0))
        for name, qty, rev in stock_rows
    ]

    alert_rows = (
        await db.execute(
            select(Product, Market)
            .join(Market, Market.id == Product.market_id)
            .where(Market.owner_id == user.id, Product.stock <= Product.min_stock)
            .order_by((Product.stock - Product.min_stock).asc())
            .limit(20)
        )
    ).all()
    low_stock_alerts = [
        LowStockAlert(
            product_id=p.id,
            product_name=p.name,
            market_id=p.market_id,
            market_name=m.name,
            stock=p.stock,
            min_stock=p.min_stock,
            status="esgotado" if p.stock <= 0 else "baixo",
        )
        for p, m in alert_rows
    ]

    markets = (await db.execute(select(Market).where(Market.owner_id == user.id))).scalars().all()
    overview = []
    for m in markets:
        row = (
            await db.execute(
                select(
                    func.count(Product.id),
                    func.coalesce(func.sum(Product.stock * Product.price), 0),
                    func.count(Product.id).filter(Product.stock <= Product.min_stock),
                    func.count(Product.id).filter(Product.status == "processing"),
                ).where(Product.market_id == m.id)
            )
        ).one()
        overview.append(
            MarketOverview(
                market_id=m.id,
                name=m.name,
                customers_per_day=m.customers_per_day,
                replenishment_cycle_days=m.replenishment_cycle_days,
                products_count=int(row[0]),
                stock_value=Decimal(row[1] or 0),
                low_stock_count=int(row[2] or 0),
                processing_count=int(row[3] or 0),
            )
        )

    return AnalyticsOut(
        from_date=date_from,
        to_date=date_to,
        stats=stats,
        previous=previous,
        revenue_change_pct=_pct_change(stats.revenue, previous.revenue),
        sales_change_pct=_pct_change(Decimal(stats.sales_count), Decimal(previous.sales_count)),
        top_products=top_products,
        revenue_by_category=revenue_by_category,
        daily_series=daily_series,
        stock_by_category=stock_by_category,
        low_stock_alerts=low_stock_alerts,
        markets_overview=overview,
    )