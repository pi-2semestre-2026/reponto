from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ImportBatch
from app.routers.dep import get_current_user, get_owned_market
from app.services.categorizer import process_product_background
from app.services.importer import DuplicateImport, ImportError_, apply_import, parse_file, preview
from app.services.recommender import recalc_products

router = APIRouter(tags=["imports"])


async def _read(file: UploadFile) -> bytes:
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="Arquivo vazio.")
    return raw


@router.post("/markets/{market_id}/import/preview")
async def preview_import(file: UploadFile = File(...), market=Depends(get_owned_market)):
    """Parse the ERP/PDV export and show what would be imported. Writes nothing."""
    raw = await _read(file)
    try:
        parsed = parse_file(raw)
    except ImportError_ as e:
        raise HTTPException(status_code=422, detail=str(e))
    return preview(parsed, file.filename or "arquivo.csv")


@router.post("/markets/{market_id}/import", status_code=201)
async def run_import(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    market=Depends(get_owned_market),
    db: AsyncSession = Depends(get_db),
):
    """Import sales history or the product catalog exported by the ERP/PDV.

    New products are categorized by the AI in background; existing ones get
    their recommendation recalculated with the new history."""
    raw = await _read(file)
    try:
        parsed = parse_file(raw)
        result = await apply_import(db, market, user, parsed, raw, file.filename or "arquivo.csv")
    except DuplicateImport as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ImportError_ as e:
        raise HTTPException(status_code=422, detail=str(e))

    for pid in result.pop("created_ids"):
        background.add_task(process_product_background, pid)
    updated = result.pop("updated_ids")
    if updated:
        background.add_task(recalc_products, updated, "import")
    return result


@router.get("/markets/{market_id}/imports")
async def list_imports(market=Depends(get_owned_market), db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(ImportBatch).where(ImportBatch.market_id == market.id).order_by(ImportBatch.created_at.desc()).limit(20)
        )
    ).scalars().all()
    return [
        {
            "id": str(b.id),
            "filename": b.filename,
            "kind": b.kind,
            "rows": b.rows,
            "products_created": b.products_created,
            "products_updated": b.products_updated,
            "sales_created": b.sales_created,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        }
        for b in rows
    ]
