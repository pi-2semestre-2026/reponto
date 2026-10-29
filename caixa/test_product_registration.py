"""Cadastro repetido: merge, confirmação, concorrência e isolamento reais."""
import asyncio
import uuid
from decimal import Decimal

import httpx
from sqlalchemy import delete, select

from app.database import SessionLocal, engine
from app.models import Market, Product, StockAdjustment, User
from app.security import create_access_token, hash_password


async def main():
    owner, other, market_id = [uuid.uuid4() for _ in range(3)]
    try:
        async with SessionLocal() as db:
            db.add_all([User(id=user_id, name="Cadastro teste", email=f"cadastro-{user_id}@example.com", hashed_password=hash_password(uuid.uuid4().hex)) for user_id in (owner, other)])
            await db.flush()
            db.add(Market(id=market_id, owner_id=owner, name="Mercado cadastro teste"))
            await db.commit()
        async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=60, headers={"Authorization": "Bearer " + create_access_token(owner)}) as client:
            path = f"/markets/{market_id}/products"
            base = {"name": "Arroz Integral", "price": 10, "cost": 4, "stock": 5, "unit": "kg"}

            async def register(expected, **changes):
                response = await client.post(path, json={**base, **changes})
                assert response.status_code == expected, response.text
                return response.json()

            first = await register(202)
            assert first["stock_added"] is False
            same = await register(200, name="  ARROZ  INTEGRAL  ", stock=2)
            assert same["id"] == first["id"] and same["stock_added"] is True
            assert Decimal(same["stock"]) == 7

            for changes in ({"price": 12}, {"cost": 5}, {"price": 12, "cost": 5}):
                conflict = await register(409, **changes)
                assert conflict["detail"]["code"] == "duplicate_product"
                existing = conflict["detail"]["existing_product"]
                assert existing["id"] == first["id"]
                assert Decimal(existing["price"]) == 10 and Decimal(existing["cost"]) == 4
            # Cancelar o aviso não faz uma segunda chamada; o conflito não grava nada.
            async with SessionLocal() as db:
                products = (await db.execute(select(Product).where(Product.market_id == market_id))).scalars().all()
                assert len(products) == 1 and products[0].stock == 7
                adjustments = (await db.execute(select(StockAdjustment).where(StockAdjustment.product_id == uuid.UUID(first["id"])))).scalars().all()
                assert len(adjustments) == 1 and adjustments[0].delta == 2

            added = await register(200, price=12, cost=5, stock=3, duplicate_action="add_stock", existing_product_id=first["id"])
            assert added["id"] == first["id"] and Decimal(added["stock"]) == 10
            assert Decimal(added["price"]) == 10 and Decimal(added["cost"]) == 4

            new = await register(202, price=12, cost=5, stock=3, duplicate_action="create_new")
            assert new["id"] != first["id"]
            repeated = await register(200, price=12, cost=5, stock=1)
            assert repeated["id"] == new["id"] and Decimal(repeated["stock"]) == 4

            await register(409, unit="g", stock=1)
            await register(409, unit="g", stock=1, duplicate_action="add_stock", existing_product_id=first["id"])
            separate_unit = await register(202, unit="g", stock=1, duplicate_action="create_new")
            assert separate_unit["unit"] == "g"
            await register(409, stock=1, duplicate_action="add_stock", existing_product_id=str(uuid.uuid4()))

            # Não duplica o produto nem perde incrementos em cadastros concorrentes.
            requests = [client.post(path, json={**base, "name": "Feijão simultâneo", "stock": 1}) for _ in range(6)]
            responses = await asyncio.gather(*requests)
            assert sorted(r.status_code for r in responses) == [200, 200, 200, 200, 200, 202], [r.text for r in responses]
            assert len({r.json()["id"] for r in responses}) == 1
            async with SessionLocal() as db:
                simultaneous = (await db.execute(select(Product).where(Product.market_id == market_id, Product.name == "Feijão simultâneo"))).scalar_one()
                assert simultaneous.stock == 6

            foreign = await client.post(path, json={**base, "duplicate_action": "add_stock", "existing_product_id": first["id"]}, headers={"Authorization": "Bearer " + create_access_token(other)})
            assert foreign.status_code == 404
            await register(422, price="1.001")
            await register(422, stock="NaN")
        print("OK: nomes equivalentes somam estoque; divergências não gravam sem decisão; adicionar preserva preços; criar novo mantém registros separados.")
        print("OK: custo/preço isolados, unidades incompatíveis, seis cadastros simultâneos e isolamento entre contas.")
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(Market).where(Market.owner_id.in_([owner, other])))
            await db.execute(delete(User).where(User.id.in_([owner, other])))
            await db.commit()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
