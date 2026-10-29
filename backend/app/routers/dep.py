import uuid

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Market, User
from app.security import decode_token

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Não autenticado")
    user_id = decode_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    return user


async def get_owned_market(
    market_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Market:
    market = await db.get(Market, market_id)
    if market is None or market.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Mercado não encontrado")
    return market