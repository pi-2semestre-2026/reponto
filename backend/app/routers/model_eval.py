from fastapi import APIRouter, Depends

from app.routers.dep import get_current_user
from app.services import evaluation
from app.services.ml import rate_model
from app.services.weekly_model import weekly_model

router = APIRouter(prefix="/ml", tags=["ml"])


@router.get("/evaluation")
async def get_evaluation(user=Depends(get_current_user)):
    """Walk-forward backtest LightGBM vs. moving average (status while running)."""
    result = evaluation.status()
    if result.get("status") == "idle":
        evaluation.start()
        result = evaluation.status()
    result["production_model"] = {
        "ready": weekly_model.ready,
        "kind": "LightGBM semanal (Tweedie) para produtos com 8+ semanas de vendas; antes disso, padrão sazonal da categoria + vendas recentes",
        "seasonal_ready": rate_model.ready,
        "trained_through": weekly_model.meta.get("trained_through"),
    }
    return result


@router.post("/evaluation/run")
async def rerun_evaluation(user=Depends(get_current_user)):
    return {"status": evaluation.start(force=True)}
