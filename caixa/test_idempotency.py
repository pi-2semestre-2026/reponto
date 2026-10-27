"""Retries through nginx must reuse a committed sale, including concurrent requests."""
import asyncio
import uuid
from decimal import Decimal
import httpx
from sqlalchemy import delete, func, select
from app.database import SessionLocal, engine
from app.models import User, Market, Product, Sale
from app.security import create_access_token, hash_password

async def main():
    owner, other, market, product, other_market, other_product = [uuid.uuid4() for _ in range(6)]
    key = str(uuid.uuid4())
    try:
        async with SessionLocal() as db:
            db.add_all([User(id=u, name='Idempotency test', email=f'idempotency-{u}@example.com', hashed_password=hash_password(uuid.uuid4().hex)) for u in (owner, other)])
            await db.flush()
            db.add_all([Market(id=market,owner_id=owner,name='Retry test'),Market(id=other_market,owner_id=other,name='Isolation test')])
            await db.flush()
            db.add_all([Product(id=product,market_id=market,name='Test kg',unit='kg',stock=10,price=10,status='ready'),Product(id=other_product,market_id=other_market,name='Other',stock=10,price=10,status='ready')])
            await db.commit()
        headers = {'Authorization':'Bearer '+create_access_token(owner),'Idempotency-Key':key}
        body = {'market_id':str(market),'items':[{'product_id':str(product),'quantity':'1.250'}]}
        async with httpx.AsyncClient(base_url='http://caixa/api',timeout=30) as client:
            responses = await asyncio.gather(*[client.post('/sales',headers=headers,json=body) for _ in range(6)])
            assert all(r.status_code == 201 for r in responses), [r.text for r in responses]
            assert len({r.json()['id'] for r in responses}) == 1
            assert all(r.json()['items'][0]['unit'] == 'kg' for r in responses)
            sale_id = responses[0].json()['id']
            async with SessionLocal() as db:
                assert (await db.get(Product,product)).stock == Decimal('8.750')
                assert await db.scalar(select(func.count()).select_from(Sale).where(Sale.market_id==market)) == 1
            changed = {**body,'items':[{'product_id':str(product),'quantity':'2'}]}
            assert (await client.post('/sales',headers=headers,json=changed)).status_code == 409
            assert (await client.post('/sales',headers={'Idempotency-Key':key},json=body)).status_code == 401
            other_headers = {'Authorization':'Bearer '+create_access_token(other),'Idempotency-Key':key}
            other_body = {'market_id':str(other_market),'items':[{'product_id':str(other_product),'quantity':'1'}]}
            assert (await client.post('/sales',headers=other_headers,json=other_body)).status_code == 201
            assert (await client.post('/sales/'+sale_id+'/cancel',headers=headers)).status_code == 200
            retry = await client.post('/sales',headers=headers,json=body)
            assert retry.json()['id'] == sale_id and retry.json()['status'] == 'cancelled'
            async with SessionLocal() as db:
                assert (await db.get(Product,product)).stock == Decimal('10.000')
            # A rejected request can be corrected: no idempotency record was committed.
            retry_headers = {**headers,'Idempotency-Key':str(uuid.uuid4())}
            invalid = {**body,'items':[{'product_id':str(product),'quantity':'100'}]}
            assert (await client.post('/sales',headers=retry_headers,json=invalid)).status_code == 400
            assert (await client.post('/sales',headers=retry_headers,json=body)).status_code == 201
        print('OK: seis reenvios simultâneos geram uma venda e uma baixa; conflito, isolamento, cancelamento e rollback preservados.')
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(Market).where(Market.owner_id.in_([owner,other])))
            await db.execute(delete(User).where(User.id.in_([owner,other])))
            await db.commit()
        await engine.dispose()

asyncio.run(main())
