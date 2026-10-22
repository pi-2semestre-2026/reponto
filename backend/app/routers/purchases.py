"""Purchase list: turns the recommendations into the cycle's shopping list and
closes the loop when the goods arrive (stock goes up, recommendation updates)."""

import datetime as dt
import math
from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Product, RecommendationLog, StockAdjustment
from app.routers.dep import get_owned_market
from app.schemas import PurchaseReceiveIn
from app.services.clock import local_date, today_local
from app.services.recommender import recalc_product, recalc_products

router = APIRouter(tags=["purchases"])

PRIORITY = {"esgotado": 0, "comprar": 1, "atencao": 2}


@router.get("/markets/{market_id}/purchase-list")
async def purchase_list(market=Depends(get_owned_market), db: AsyncSession = Depends(get_db)):
    """Products that will not last the replenishment cycle, with how much to buy
    to reach the recommended level (order-up-to policy)."""
    products = (
        await db.execute(select(Product).where(Product.market_id == market.id, Product.status == "ready"))
    ).scalars().all()

    # The reorder point depends on which weekdays come next: refresh products
    # not recalculated today so Monday-heavy items rise before Monday.
    last_calc = dict(
        (
            await db.execute(
                select(RecommendationLog.product_id, func.max(RecommendationLog.created_at))
                .join(Product, Product.id == RecommendationLog.product_id)
                .where(Product.market_id == market.id)
                .group_by(RecommendationLog.product_id)
            )
        ).all()
    )
    today = today_local()
    stale = [p for p in products if last_calc.get(p.id) is None or local_date(last_calc[p.id]) < today]
    for p in stale:
        await recalc_product(db, p, market, "daily")
    if stale:
        await db.commit()

    cycle = max(1, market.replenishment_cycle_days)
    items = []
    for p in products:
        stock = float(p.stock or 0)
        rate = float(p.learned_rate or 0)
        minimum = float(p.min_stock or 0)
        target = float(p.recommended_quantity or 0)
        if stock <= 0:
            status = "esgotado"
        elif stock <= minimum:
            status = "comprar"
        elif rate > 0 and stock < rate * cycle:
            status = "atencao"
        else:
            continue
        buy = max(0, math.ceil(target - stock - 1e-9))
        if buy == 0:
            continue
        cost = Decimal(p.cost or 0)
        items.append(
            {
                "product_id": str(p.id),
                "name": p.name,
                "sku": p.sku,
                "unit": p.unit,
                "category_name": p.category_name,
                "status": status,
                "stock": round(stock, 3),
                "min_stock": round(minimum, 3),
                "target_stock": round(target, 3),
                "daily_rate": round(rate, 3),
                "coverage_days": round(stock / rate, 1) if rate > 0 else None,
                "buy_quantity": buy,
                "unit_cost": float(cost) if cost > 0 else None,
                "line_cost": float((cost * buy).quantize(Decimal("0.01"))) if cost > 0 else None,
                "confidence": p.confidence,
            }
        )
    items.sort(key=lambda i: (PRIORITY[i["status"]], i["coverage_days"] if i["coverage_days"] is not None else 0))
    known = [i["line_cost"] for i in items if i["line_cost"] is not None]
    return {
        "market_id": str(market.id),
        "market_name": market.name,
        "cycle_days": cycle,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "items": items,
        "totals": {
            "items": len(items),
            "urgent": sum(1 for i in items if i["status"] in ("esgotado", "comprar")),
            "units": sum(i["buy_quantity"] for i in items),
            "estimated_cost": round(sum(known), 2),
            "missing_cost": len(items) - len(known),
        },
    }


@router.post("/markets/{market_id}/purchases")
async def receive_purchase(
    payload: PurchaseReceiveIn,
    background: BackgroundTasks,
    market=Depends(get_owned_market),
    db: AsyncSession = Depends(get_db),
):
    """Register the goods that arrived: stock goes up and every product is recalculated."""
    ids = [i.product_id for i in payload.items]
    products = {
        p.id: p
        for p in (
            await db.execute(select(Product).where(Product.id.in_(ids), Product.market_id == market.id).with_for_update())
        ).scalars()
    }
    if len(products) != len(set(ids)):
        raise HTTPException(status_code=400, detail="Produto não encontrado neste mercado")
    for item in payload.items:
        p = products[item.product_id]
        p.stock = (Decimal(p.stock or 0) + item.quantity).quantize(Decimal("0.001"))
        db.add(StockAdjustment(product_id=p.id, delta=item.quantity, reason=payload.note or "Compra recebida"))
    await db.commit()
    background.add_task(recalc_products, ids, "purchase")
    return {"received": len(payload.items), "units": float(sum(i.quantity for i in payload.items))}
