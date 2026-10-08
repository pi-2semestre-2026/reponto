"""Admin game API — /admin/simulator.

Mounted optionally (see mount.py). Requires the same Bearer auth as the
rest of the app, but never touches user data: sessions live in memory.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.routers.dep import get_current_user
from simulator import store
from simulator.engine import SimulationEngine
from simulator.llm import coach_report
from simulator.metrics import full_report
from simulator.scenarios import SCENARIOS

router = APIRouter(prefix="/admin/simulator", tags=["simulator"])


class CreateIn(BaseModel):
    scenario: str = "bairro"
    days: int = Field(default=90, ge=7, le=1095)
    cycle_days: int = Field(default=7, ge=1, le=30)
    seed: int | None = None


class StepIn(BaseModel):
    days: int = Field(default=1, ge=1, le=90)


def _engine_or_404(sid: str) -> SimulationEngine:
    engine = store.get(sid)
    if engine is None:
        raise HTTPException(status_code=404, detail="Partida não encontrada (expirada?)")
    return engine


@router.get("/scenarios")
async def list_scenarios(user=Depends(get_current_user)):
    return [
        {
            "key": s.key,
            "name": s.name,
            "description": s.description,
            "customers_per_day": s.customers_per_day,
            "products": len(s.product_keys),
        }
        for s in SCENARIOS.values()
    ]


@router.post("/sessions")
async def create_session(payload: CreateIn, user=Depends(get_current_user)):
    try:
        engine = SimulationEngine(
            scenario_key=payload.scenario,
            days=payload.days,
            cycle_days=payload.cycle_days,
            seed=payload.seed,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    sid = store.create(engine)
    return {"sid": sid, "snapshot": engine.snapshot()}


@router.post("/sessions/{sid}/step")
async def step(sid: str, payload: StepIn, user=Depends(get_current_user)):
    engine = _engine_or_404(sid)
    reports = []
    for _ in range(payload.days):
        if engine.done:
            break
        reports.append(engine.step())
    return {"reports": reports, "snapshot": engine.snapshot()}


@router.get("/sessions/{sid}")
async def get_session(sid: str, user=Depends(get_current_user)):
    engine = _engine_or_404(sid)
    return {"sid": sid, "snapshot": engine.snapshot()}


@router.get("/sessions/{sid}/report")
async def get_report(sid: str, user=Depends(get_current_user)):
    engine = _engine_or_404(sid)
    if not engine.done and engine.day_index == 0:
        raise HTTPException(status_code=400, detail="Jogue alguns dias antes de pedir o relatório")
    report = full_report(engine)
    report["config"] = {
        "scenario": engine.scenario_name,
        "customers_per_day": engine.customers_per_day,
        "days": engine.day_index,
        "cycle_days": engine.cycle_days,
        "seed": engine.seed,
    }
    coach = await coach_report(report)
    return {"report": report, "coach": coach}


@router.delete("/sessions/{sid}")
async def delete_session(sid: str, user=Depends(get_current_user)):
    return {"ok": store.delete(sid)}
