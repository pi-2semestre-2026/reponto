"""Testa busca, ordenação e paginação real pelo proxy do caixa."""
import asyncio
import datetime as dt
import uuid
from decimal import Decimal

import httpx
from sqlalchemy import delete

from app.database import SessionLocal, engine
from app.models import Market, Product, Sale, SaleItem, User
from app.security import create_access_token, hash_password


async def main():
    owner, other, market_id, rice_id, banana_id = [uuid.uuid4() for _ in range(5)]
    try:
        async with SessionLocal() as db:
            for user_id in (owner, other):
                db.add(User(id=user_id, name="Teste histórico", email=f"history-{user_id}@example.com", hashed_password=hash_password(uuid.uuid4().hex)))
            await db.flush()
            db.add(Market(id=market_id, owner_id=owner, name="Teste histórico"))
            await db.flush()
            db.add_all([
                Product(id=rice_id, market_id=market_id, name="Arroz", stock=100, price=10),
                Product(id=banana_id, market_id=market_id, name="Banana", stock=100, price=10),
            ])
            await db.flush()
            ids = []
            for i in range(1, 16):
                sale = Sale(id=uuid.uuid4(), market_id=market_id, user_id=owner, total=i * 10,
                            sold_at=dt.datetime(2026, 10, 26, 12, i, tzinfo=dt.timezone.utc))
                sale.items.append(SaleItem(product_id=rice_id, product_name="Arroz", quantity=i, unit_price=10, subtotal=i * 10))
                db.add(sale)
                ids.append(str(sale.id))
            mixed = Sale(id=uuid.uuid4(), market_id=market_id, user_id=owner, total=1000,
                         sold_at=dt.datetime(2026, 10, 26, 13, tzinfo=dt.timezone.utc))
            mixed.items.extend([
                SaleItem(product_id=rice_id, product_name="Arroz", quantity=Decimal("1.250"), unit_price=400, subtotal=500),
                SaleItem(product_id=banana_id, product_name="Banana", quantity=3, unit_price=Decimal("166.67"), subtotal=500),
            ])
            db.add(mixed)
            await db.commit()

        async with httpx.AsyncClient(base_url="http://caixa/api", headers={"Authorization": "Bearer " + create_access_token(owner)}) as client:
            async def history(**params):
                response = await client.get("/sales/history", params={"market_id": str(market_id), **params})
                assert response.status_code == 200, response.text
                return response.json()

            # The main sales screen uses all markets, pagination and local calendar dates.
            all_sales = await client.get("/sales/history", params={"page_size": 10, "date_from": "2026-10-26", "date_to": "2026-10-26"})
            assert all_sales.status_code == 200 and all_sales.json()["total"] == 16
            next_page = await client.get("/sales/history", params={"page_size": 10, "page": 2, "date_from": "2026-10-26", "date_to": "2026-10-26"})
            assert len(next_page.json()["items"]) == 6
            assert not ({s["id"] for s in all_sales.json()["items"]} & {s["id"] for s in next_page.json()["items"]})
            assert (await history(date_from="2026-10-27", date_to="2026-10-27"))["total"] == 0
            assert (await client.get("/sales/history", params={"date_from":"2026-10-27", "date_to":"2026-10-26"})).status_code == 422
            isolated = await client.get("/sales/history", headers={"Authorization": "Bearer " + create_access_token(other)})
            assert isolated.json()["total"] == 0
            first = await history(order="value_desc")
            second = await history(order="value_desc", page=2)
            third = await history(order="value_desc", page=3)
            assert first["total"] == 16 and first["page_size"] == 7
            assert [len(p["items"]) for p in (first, second, third)] == [7, 7, 2]
            combined = first["items"] + second["items"] + third["items"]
            assert len({s["id"] for s in combined}) == 16
            totals = [Decimal(s["total"]) for s in combined]
            assert totals == sorted(totals, reverse=True)
            assert (await history(order="value_asc"))["items"][0]["id"] == ids[0]
            assert (await history(order="quantity_desc"))["items"][0]["id"] == ids[-1]
            assert (await history(order="quantity_asc"))["items"][0]["id"] == ids[0]
            assert (await history(product="aRrOz"))["total"] == 16
            fractional = await history(product="Arroz", quantity="1.250")
            assert fractional["total"] == 1 and fractional["items"][0]["id"] == str(mixed.id)
            assert (await history(product="Banana", quantity="1.250"))["total"] == 0
            assert (await history(product="%"))["total"] == 0
            assert (await history(product="Arroz", page=999))["page"] == 3
            assert (await history(product="inexistente", page=999))["page"] == 1
            for params in ({"quantity": "0"}, {"quantity": "NaN"}, {"page": 0}, {"page_size": 101}, {"order": "invalid"}):
                assert (await client.get("/sales/history", params={"market_id": str(market_id), **params})).status_code == 422
            response = await client.get("/sales/history", params={"market_id": str(market_id)}, headers={"Authorization": "Bearer " + create_access_token(other)})
            assert response.status_code == 200 and response.json()["total"] == 0
            # More than the old 500-row limit: every sale remains reachable.
            async with SessionLocal() as db:
                db.add_all([Sale(market_id=market_id, user_id=owner, total=1,
                                sold_at=dt.datetime(2026, 10, 26, 14, tzinfo=dt.timezone.utc)) for _ in range(500)])
                await db.commit()
            pages = [await history(page=page, page_size=100) for page in range(1, 7)]
            assert all(p["total"] == 516 for p in pages)
            assert len({sale["id"] for p in pages for sale in p["items"]}) == 516
        print("OK: páginas 7/7/2, ordenações, busca por item e quantidade decimal, isolamento e validação.")
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(Market).where(Market.owner_id.in_([owner, other])))
            await db.execute(delete(User).where(User.id.in_([owner, other])))
            await db.commit()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
