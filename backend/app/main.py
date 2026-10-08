import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.bootstrap import prepare_data
from app.config import get_settings
from app.routers import analytics, auth, categories, markets, products, sales

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

bootstrap_done = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bootstrap_done
    if not bootstrap_done:
        await prepare_data()
        bootstrap_done = True
    yield


app = FastAPI(title="Reponto API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().FRONTEND_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(markets.router)
app.include_router(products.router)
app.include_router(sales.router)
app.include_router(categories.router)
app.include_router(analytics.router)

try:
    from simulator import register as register_simulator

    register_simulator(app)
except ImportError:
    logging.getLogger(__name__).info("simulator package not present — skipping")


@app.get("/health")
async def health():
    return {"status": "ok"}