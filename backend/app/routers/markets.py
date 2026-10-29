import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Market
from app.routers.dep import get_current_user, get_owned_market
from app.schemas import MarketIn, MarketOut
from app.services.recommender import recalc_market_products

router = APIRouter(prefix="/markets", tags=["markets"])

CYCLE_DAYS = {"diario": 1, "semanal": 7, "quinzenal": 15, "mensal": 30}


@router.get("", response_model=list[MarketOut])
async def list_markets(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Market).where(Market.owner_id == user.id).order_by(Market.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=MarketOut, status_code=201)
async def create_market(payload: MarketIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    unit = payload.cycle_unit.lower().strip()
    days = CYCLE_DAYS.get(unit, payload.replenishment_cycle_days)
    market = Market(
        owner_id=user.id,
        name=payload.name.strip(),
        location=payload.location.strip(),
        customers_per_day=payload.customers_per_day,
        replenishment_cycle_days=days,
        cycle_unit=unit,
    )
    db.add(market)
    await db.commit()
    await db.refresh(market)
    return market


@router.get("/{market_id}", response_model=MarketOut)
async def get_market(market: Market = Depends(get_owned_market)):
    return market


@router.patch("/{market_id}", response_model=MarketOut)
async def update_market(
    payload: MarketIn,
    background: BackgroundTasks,
    market: Market = Depends(get_owned_market),
    db: AsyncSession = Depends(get_db),
):
    unit = payload.cycle_unit.lower().strip()
    days = CYCLE_DAYS.get(unit, payload.replenishment_cycle_days)
    rate_relevant = (
        market.customers_per_day != payload.customers_per_day or market.replenishment_cycle_days != days
    )
    market.name = payload.name.strip()
    market.location = payload.location.strip()
    market.customers_per_day = payload.customers_per_day
    market.cycle_unit = unit
    market.replenishment_cycle_days = days
    db.add(market)
    await db.commit()
    await db.refresh(market)
    if rate_relevant:
        background.add_task(recalc_market_products, "market_updated", market.id)
    return market


@router.delete("/{market_id}", status_code=204)
async def delete_market(market: Market = Depends(get_owned_market), db: AsyncSession = Depends(get_db)):
    await db.delete(market)
    await db.commit()