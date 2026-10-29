"""Executar no contêiner backend; cria e remove apenas dados próprios de teste."""
import asyncio
import json
import uuid
from decimal import Decimal
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sqlalchemy import delete, select

from app.config import get_settings
from app.database import SessionLocal, engine
from app.models import Market, Product, Sale, SaleItem, User


def request(path, body=None, token=None, expected=200):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(
        "http://caixa/api" + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
    )
    try:
        with urlopen(req, timeout=120) as response:
            status, data = response.status, json.load(response)
    except HTTPError as error:
        status, data = error.code, json.load(error)
    if status != expected:
        raise AssertionError(f"{path}: esperado HTTP {expected}, recebido {status}: {data}")
    return data


async def main():
    if get_settings().OPENROUTER_API_KEY:
        raise RuntimeError("Execute com compose.sem-ia.yml: a chave precisa estar vazia no backend.")
    email = f"caixa-{uuid.uuid4().hex}@example.com"
    try:
        auth = await asyncio.to_thread(request, "/auth/register", {
            "name": "Teste Caixa", "email": email, "password": uuid.uuid4().hex,
        }, expected=201)
        token = auth["access_token"]
        market = await asyncio.to_thread(request, "/markets", {"name": "Mercado de teste Caixa"}, token, 201)
        product = await asyncio.to_thread(request, f"/markets/{market['id']}/products", {
            "name": "Arroz teste caixa", "price": "10.00", "stock": "5.000", "unit": "kg",
        }, token, 202)
        payload = {"market_id": market["id"], "items": [{"product_id": product["id"], "quantity": "1.250"}]}
        await asyncio.to_thread(request, "/sales", payload, expected=401)
        await asyncio.to_thread(request, "/sales", {
            "market_id": market["id"], "items": [{"product_id": product["id"], "quantity": "6"}],
        }, token, 400)
        async with SessionLocal() as db:
            assert (await db.execute(select(Sale).where(Sale.market_id == uuid.UUID(market["id"])))).scalars().all() == []
            stored = await db.get(Product, uuid.UUID(product["id"]))
            assert stored.stock == Decimal("5.000"), "Venda rejeitada alterou estoque"
        sale = await asyncio.to_thread(request, "/sales", payload, token, 201)
        async with SessionLocal() as db:
            stored_sale = await db.get(Sale, uuid.UUID(sale["id"]))
            stored_product = await db.get(Product, uuid.UUID(product["id"]))
            items = (await db.execute(select(SaleItem).where(SaleItem.sale_id == stored_sale.id))).scalars().all()
            assert stored_sale.status == "completed"
            assert stored_sale.market_id == uuid.UUID(market["id"])
            assert stored_sale.total == Decimal("12.50")
            assert stored_product.stock == Decimal("3.750")
            assert len(items) == 1
            assert items[0].product_id == stored_product.id
            assert items[0].quantity == Decimal("1.250")
            assert items[0].unit_price == Decimal("10.00")
            assert items[0].subtotal == Decimal("12.50")
            assert items[0].unit == "kg"
            assert sale["items"][0]["unit"] == "kg"
            stored_product.unit = "g"
            await db.commit()
        saved = await asyncio.to_thread(request, f"/sales/{sale['id']}", token=token)
        assert saved["items"][0]["unit"] == "kg", "Unidade da venda deve permanecer a do momento da compra"
        history = await asyncio.to_thread(request, f"/sales?market_id={market['id']}", token=token)
        assert any(s["id"] == sale["id"] for s in history)
        print("OK: venda e item persistidos, total R$ 12,50 e estoque 3,750; sem chave de IA.")
        print("OK: venda sem login e estoque insuficiente foram rejeitados sem gravação.")
    finally:
        async with SessionLocal() as db:
            user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if user:
                await db.execute(delete(Market).where(Market.owner_id == user.id))
                await db.execute(delete(User).where(User.id == user.id))
                await db.commit()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
