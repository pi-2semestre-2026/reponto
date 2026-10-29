from fastapi import APIRouter, Depends

from app.routers.dep import get_current_user
from app.services import evaluation
from app.services.ml import rate_model

router = APIRouter(prefix="/ml", tags=["ml"])


@router.get("/evaluation")
async def get_evaluation(user=Depends(get_current_user)):
    """Walk-forward backtest LightGBM vs. moving average (status while running)."""
    result = evaluation.status()
    if result.get("status") == "idle":
        evaluation.start()
        result = evaluation.status()
    result["production_model"] = {
        "ready": rate_model.ready,
        "kind": "LightGBM sazonal (mês × dia da semana × porte da loja)",
        "overall_mean": rate_model.overall_mean,
    }
    return result


@router.post("/evaluation/run")
async def rerun_evaluation(user=Depends(get_current_user)):
    return {"status": evaluation.start(force=True)}
