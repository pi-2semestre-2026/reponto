import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Category, Product
from app.routers.dep import get_current_user
from app.schemas import CategoryIn, CategoryOut

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
async def list_categories(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).order_by(Category.is_seed.desc(), Category.name))
    return result.scalars().all()


@router.post("", response_model=CategoryOut, status_code=201)
async def create_category(payload: CategoryIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    name = payload.name.strip()
    existing = (
        await db.execute(select(Category).where(func.lower(Category.name) == name.lower()))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Já existe uma categoria com esse nome")
    category = Category(name=name, description=payload.description.strip(), keywords=payload.keywords.strip(), is_seed=False)
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


@router.patch("/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: uuid.UUID,
    payload: CategoryIn,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    name = payload.name.strip()
    dup = (
        await db.execute(select(Category).where(func.lower(Category.name) == name.lower(), Category.id != category.id))
    ).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail="Já existe uma categoria com esse nome")
    category.name = name
    category.description = payload.description.strip()
    category.keywords = payload.keywords.strip()
    await db.commit()
    await db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=204)
async def delete_category(category_id: uuid.UUID, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    if category.is_seed:
        raise HTTPException(status_code=400, detail="Categorias padrão não podem ser excluídas")
    in_use = (
        await db.execute(select(func.count(Product.id)).where(Product.category_id == category.id))
    ).scalar() or 0
    if in_use:
        raise HTTPException(status_code=409, detail=f"Existem {in_use} produto(s) nesta categoria")
    await db.delete(category)
    await db.commit()