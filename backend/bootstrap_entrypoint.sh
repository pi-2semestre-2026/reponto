#!/bin/sh
set -e

echo "[entrypoint] waiting for database..."
until python -c "
import asyncio, os, asyncpg

async def ping():
    url = os.environ['DATABASE_URL'].replace('postgresql+asyncpg://', 'postgresql://')
    conn = await asyncpg.connect(url, timeout=3)
    await conn.close()

asyncio.run(ping())
" 2>/dev/null; do
  sleep 2
done

echo "[entrypoint] running bootstrap (tables, seed, ingest-once, model)..."
python -m app.bootstrap || echo "[entrypoint] bootstrap failed — API will still start with static priors"

echo "[entrypoint] starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000