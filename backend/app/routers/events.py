"""SSE stream; bearer authentication stays in headers, never URL parameters."""
import asyncio

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import User
from app.routers.dep import bearer_scheme
from app.security import decode_token
from app.services.events import CHANNEL

router = APIRouter(tags=["events"])


@router.get("/events")
async def events(credentials=Depends(bearer_scheme)):
    user_id = decode_token(credentials.credentials) if credentials else None
    if user_id is None:
        raise HTTPException(status_code=401, detail="Não autenticado")
    # Release the SQLAlchemy session before opening a long-lived stream.
    async with SessionLocal() as db:
        if await db.scalar(select(User.id).where(User.id == user_id)) is None:
            raise HTTPException(status_code=401, detail="Usuário não encontrado")

    async def stream():
        connection = await asyncpg.connect(
            get_settings().DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://"),
            timeout=10,
        )
        pending = asyncio.Queue(maxsize=1)

        def changed(conn, pid, channel, payload):
            if payload == str(user_id) and pending.empty():
                pending.put_nowait(True)

        try:
            await connection.add_listener(CHANNEL, changed)
            # Initial refresh after LISTEN also catches changes during reconnect.
            yield "event: ready\ndata: {}\n\n"
            while decode_token(credentials.credentials) == user_id:
                if connection.is_closed():
                    break
                try:
                    await asyncio.wait_for(pending.get(), timeout=15)
                    yield "event: change\ndata: {}\n\n"
                except asyncio.TimeoutError:
                    # Keep proxy connections alive; no query/poll of sales.
                    yield ": keepalive\n\n"
        finally:
            await asyncio.shield(connection.close(timeout=5))

    return StreamingResponse(stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
    })
