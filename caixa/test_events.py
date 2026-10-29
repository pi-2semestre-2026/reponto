"""Teste real SSE pelo Nginx + triggers transacionais; executar no backend."""
import asyncio
import uuid
from decimal import Decimal

import httpx
from sqlalchemy import delete, select

from app.database import SessionLocal, engine
from app.models import Market, Product, User
from app.security import hash_password, create_access_token


async def next_event(lines):
    async for line in lines:
        if line.startswith("event: "):
            return line.removeprefix("event: ")
    raise AssertionError("Stream encerrado antes do evento")


async def main():
    owner_id, other_id, market_id, product_id = [uuid.uuid4() for _ in range(4)]
    pending = None
    try:
        async with SessionLocal() as db:
            for user_id in (owner_id, other_id):
                db.add(User(id=user_id, name="Teste SSE", email=f"sse-{user_id}@example.com", hashed_password=hash_password(uuid.uuid4().hex)))
            await db.flush()
            db.add(Market(id=market_id, owner_id=owner_id, name="Teste SSE"))
            await db.flush()
            db.add(Product(id=product_id, market_id=market_id, name="Arroz SSE", price=10, stock=5, status="ready"))
            await db.commit()

        async with httpx.AsyncClient(base_url="http://caixa/api", timeout=10) as client:
            assert (await client.get("/events")).status_code == 401
            assert (await client.get("/events", headers={"Authorization": "Bearer invalido"})).status_code == 401
            headers = {"Authorization": "Bearer " + create_access_token(owner_id)}
            async with client.stream("GET", "/events", headers=headers) as response:
                assert response.status_code == 200
                assert response.headers["content-type"].startswith("text/event-stream")
                lines = response.aiter_lines()
                assert await asyncio.wait_for(next_event(lines), 5) == "ready"
                pending = asyncio.create_task(next_event(lines))

                # Outro proprietário não deve produzir evento nesta sessão.
                async with SessionLocal() as db:
                    db.add(Market(owner_id=other_id, name="Outro proprietário SSE"))
                    await db.commit()
                assert not (await asyncio.wait({pending}, timeout=0.25))[0], "Evento de outro usuário vazou"

                # Trigger executado em transação desfeita não deve notificar.
                async with SessionLocal() as db:
                    market = await db.get(Market, market_id)
                    market.name = "Alteração desfeita"
                    await db.flush()
                    await db.rollback()
                assert not (await asyncio.wait({pending}, timeout=0.25))[0], "Rollback gerou evento"

                sale = await client.post("/sales", headers=headers, json={
                    "market_id": str(market_id), "items": [{"product_id": str(product_id), "quantity": 1}],
                })
                assert sale.status_code == 201, sale.text
                assert await asyncio.wait_for(pending, 5) == "change"
                pending = None
                assert (await client.get(f"/sales/{sale.json()['id']}", headers=headers)).status_code == 200
                products = (await client.get(f"/markets/{market_id}/products", headers=headers)).json()
                updated = next(p for p in products if p["id"] == str(product_id))
                assert Decimal(updated["stock"]) == Decimal("4")
                assert updated["learned_rate"] > 0
                async with SessionLocal() as db:
                    stored = await db.get(Product, product_id)
                    for field in ("min_stock", "max_stock", "recommended_quantity"):
                        assert Decimal(updated[field]) == getattr(stored, field)

            # Uma reconexão recebe ready para recuperar mudanças perdidas.
            async with client.stream("GET", "/events", headers=headers) as response:
                lines = response.aiter_lines()
                assert await asyncio.wait_for(next_event(lines), 5) == "ready"
                pending = asyncio.create_task(next_event(lines))
                cancelled = await client.post(f"/sales/{sale.json()['id']}/cancel", headers=headers)
                assert cancelled.status_code == 200
                assert await asyncio.wait_for(pending, 5) == "change"
                pending = None
                restored = (await client.get(f"/markets/{market_id}/products", headers=headers)).json()
                assert Decimal(next(p for p in restored if p["id"] == str(product_id))["stock"]) == Decimal("5")
        print("OK: estoque e indicadores atualizados após venda; cancelamento notifica e repõe estoque.")
        print("OK: SSE via Nginx após venda confirmada, isolamento por usuário, rollback e reconexão.")
    finally:
        if pending:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        async with SessionLocal() as db:
            await db.execute(delete(Market).where(Market.owner_id.in_([owner_id, other_id])))
            await db.execute(delete(User).where(User.id.in_([owner_id, other_id])))
            await db.commit()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
