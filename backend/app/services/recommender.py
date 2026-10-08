"""Recommendation engine — the heart of the system.

prior_rate    = baseline (typical SKU units/customer/day of the category)
                x seasonal factor (LightGBM on the Store Item Demand dataset)
                x customers/day
                (fallback: static category prior x customers/day)
observed_rate = exponentially-decayed weighted average over the window
                starting at the FIRST sale (capped to OBS_WINDOW_DAYS):
                sum(qty x 2^(-age/half_life)) / sum(day weights)
alpha         = max(0.3, n_sales_in_window / (n + 10))
final_rate    = alpha x observed + (1 - alpha) x prior

Every recalculation writes an auditable RecommendationLog row consumed by the
"How the AI calculated" panel. Retroactive sales respect their own sold_at date.
"""

import datetime as dt
import json
import logging
from decimal import Decimal

from sqlalchemy import bindparam, func, select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models import Category, CategoryPrior, Market, Product, RecommendationLog, Sale, SaleItem
from app.services.clock import LOCAL_TZ_NAME, day_bounds, local_date, today_local
from app.services.ml import rate_model
from app.services.seed_data import baseline_by_name, size_bucket_from_customers

settings = get_settings()
logger = logging.getLogger("recommender")

DEFAULT_PRIOR = 0.08
SEASONAL_FACTOR_BOUNDS = (0.5, 2.0)

TRIGGER_LABELS = {
    "product_created": "Criação do produto",
    "sale": "Venda registrada",
    "sale_cancelled": "Venda cancelada (estorno)",
    "stock_adjust": "Ajuste manual de estoque",
    "product_updated": "Produto atualizado",
    "market_updated": "Configuração do mercado alterada",
    "recalc": "Recálculo manual",
}


def _local_date(d: dt.datetime) -> dt.date:
    return local_date(d)


def decay_weight(age_days: float, half_life: float) -> float:
    return 2.0 ** (-age_days / half_life)


def window_denominator(window_days: int, half_life: float) -> float:
    """Sum of decay weights for each observed day, from window start to today.

    Today has weight 1.0; window start has weight 2^(-window_days/half_life).
    Closed-form geometric series.
    """
    if window_days < 0:
        window_days = 0
    r = 2.0 ** (-1.0 / half_life)
    return (1.0 - r ** (window_days + 1)) / (1.0 - r)


async def compute_prior_rate(session, product: Product, market: Market, today: dt.date) -> tuple[float, str, dict]:
    """Calibrated prior: baseline (units/customer/day of a typical SKU of the
    category in a physical mercado) x seasonal factor from the dataset model
    x customers/day.

    The Store Item Demand dataset only shapes the SEASONALITY (month x
    weekday x store-size index relative to the dataset-wide mean, clamped) —
    the absolute level comes from the category baselines, since the dataset's
    items are not the user's SKUs.

    The category is resolved fresh by ID — `product.category` may be stale
    (e.g. the default category loaded before the AI assigned the real one).
    Returns (rate, source, context).
    """
    size = size_bucket_from_customers(market.customers_per_day)
    cat = None
    if product.category_id is not None:
        cat = await session.get(Category, product.category_id)
    cat_name = cat.name if cat else None
    ctx = {
        "month": today.month,
        "weekday": today.weekday(),
        "size_bucket": size,
        "category_name": cat_name,
        "baseline": None,
        "seasonal_factor": None,
    }

    baseline = baseline_by_name(cat_name) if cat_name else DEFAULT_PRIOR
    ctx["baseline"] = baseline

    pred = rate_model.predict(today.month, today.weekday(), size)
    if pred is not None:
        mean = rate_model.overall_mean or 0.0
        if mean > 0:
            factor = pred / mean
            factor = max(SEASONAL_FACTOR_BOUNDS[0], min(SEASONAL_FACTOR_BOUNDS[1], factor))
        else:
            factor = 1.0
        ctx["seasonal_factor"] = round(factor, 3)
        return baseline * factor * market.customers_per_day, "model", ctx

    if cat is not None:
        row = await session.get(CategoryPrior, cat.id)
        if row is not None:
            return row.prior_rate * market.customers_per_day, "static", ctx

    return baseline * market.customers_per_day, "default", ctx


async def compute_blend(session, product: Product, market: Market) -> dict:
    """Full prior/observed blend computation. Pure calculation, no writes."""
    today = today_local()
    cycle = max(1, market.replenishment_cycle_days)
    half_life = float(settings.EMA_HALF_LIFE_DAYS)
    obs_window = int(settings.OBS_WINDOW_DAYS)

    prior_rate, prior_source, prior_ctx = await compute_prior_rate(session, product, market, today)

    first_sale_date = (
        await session.execute(
            select(
                func.min(
                    func.date(func.timezone(bindparam("app_tz_min", LOCAL_TZ_NAME, literal_execute=True), Sale.sold_at))
                )
            )
            .join(SaleItem, SaleItem.sale_id == Sale.id)
            .where(SaleItem.product_id == product.id, Sale.status == "completed")
        )
    ).scalar()
    window_start = today
    if first_sale_date is not None:
        candidate = first_sale_date if isinstance(first_sale_date, dt.date) else _local_date(first_sale_date)
        window_start = max(candidate, today - dt.timedelta(days=obs_window))
    window_days = (today - window_start).days

    rows = (
        await session.execute(
            select(SaleItem.quantity, Sale.sold_at, Sale.id)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(
                SaleItem.product_id == product.id,
                Sale.status == "completed",
                Sale.sold_at >= day_bounds(window_start, window_start)[0],
            )
        )
    ).all()

    numerator = 0.0
    n_sales = 0
    seen_sales: set = set()
    for qty, sold_at, sale_id in rows:
        sale_date = _local_date(sold_at)
        if sale_date < window_start or sale_date > today:
            continue
        age = (today - sale_date).days
        numerator += float(qty) * decay_weight(age, half_life)
        if sale_id not in seen_sales:
            seen_sales.add(sale_id)
            n_sales += 1

    denominator = window_denominator(window_days, half_life)
    observed_rate = numerator / denominator if denominator > 0 else 0.0

    notes: list[str] = []
    if n_sales == 0:
        stock = float(product.stock or 0)
        if stock > 0:
            observed_rate = stock / cycle
            alpha = 0.3
            notes.append("Sem vendas na janela: observado estimado por estoque/ciclo")
        else:
            observed_rate = 0.0
            alpha = 0.3
            notes.append("Sem vendas e sem estoque: observado zerado, prior domina")
    else:
        alpha = max(0.3, n_sales / (n_sales + 10))
        if n_sales < 3:
            notes.append("Poucas vendas: alpha no piso de 0.3, prior ainda domina")

    final_rate = alpha * observed_rate + (1 - alpha) * prior_rate
    safety = final_rate * cycle * 0.3
    min_stock = final_rate * cycle * 0.4 + safety
    recommended = final_rate * cycle * 1.2 + safety
    max_stock = final_rate * cycle * 2.0 + safety

    confidence = "baixa" if n_sales < 3 else ("media" if n_sales < 10 else "alta")

    return {
        "prior_rate": prior_rate,
        "prior_source": prior_source,
        "month": prior_ctx["month"],
        "weekday": prior_ctx["weekday"],
        "size_bucket": prior_ctx["size_bucket"],
        "category_name": prior_ctx["category_name"],
        "baseline": prior_ctx["baseline"],
        "seasonal_factor": prior_ctx["seasonal_factor"],
        "observed_rate": observed_rate,
        "alpha": alpha,
        "final_rate": final_rate,
        "safety_stock": safety,
        "min_stock": min_stock,
        "max_stock": max_stock,
        "recommended_quantity": recommended,
        "n_sales": n_sales,
        "confidence": confidence,
        "window_start": window_start,
        "window_end": today,
        "window_days": window_days,
        "numerator": numerator,
        "denominator": denominator,
        "notes": notes,
        "cycle": cycle,
        "half_life": half_life,
        "obs_window": obs_window,
    }


def _d(value: float, places: int = 3) -> Decimal:
    return Decimal(str(round(max(0.0, value), places)))


def formula_string(blend: dict) -> str:
    return (
        f"final = {blend['alpha']:.2f} × observado ({blend['observed_rate']:.3f}/d) "
        f"+ {1 - blend['alpha']:.2f} × prior ({blend['prior_rate']:.3f}/d) "
        f"= {blend['final_rate']:.3f}/d"
    )


async def recalc_product(session, product: Product, market: Market, trigger: str) -> RecommendationLog:
    """Recalculate rates for one product and persist an auditable log."""
    blend = await compute_blend(session, product, market)

    product.min_stock = _d(blend["min_stock"])
    product.max_stock = _d(blend["max_stock"])
    product.recommended_quantity = _d(blend["recommended_quantity"])
    product.learned_rate = round(blend["final_rate"], 4)
    product.prior_rate = round(blend["prior_rate"], 4)
    product.observed_rate = round(blend["observed_rate"], 4)
    product.alpha = round(blend["alpha"], 4)
    product.confidence = blend["confidence"]

    details = {
        "motivo": TRIGGER_LABELS.get(trigger, trigger),
        "formula": formula_string(blend),
        "janela_dias": blend["window_days"],
        "denominador": round(blend["denominator"], 4),
        "numerador": round(blend["numerator"], 4),
        "ciclo_dias": blend["cycle"],
        "meia_vida_dias": blend["half_life"],
        "janela_max_dias": blend["obs_window"],
        "fonte_prior": blend["prior_source"],
        "clientes_dia": market.customers_per_day,
        "prior_composicao": {
            "baseline_un_cliente_dia": blend["baseline"],
            "fator_sazonal": blend["seasonal_factor"],
            "categoria": blend["category_name"],
        },
        "contexto_modelo": {
            "categoria": blend["category_name"],
            "mes": blend["month"],
            "dia_semana": blend["weekday"],
            "porte": blend["size_bucket"],
        },
        "notas": blend["notes"],
        "seguranca": round(blend["safety_stock"], 3),
    }

    log = RecommendationLog(
        product_id=product.id,
        trigger=trigger,
        prior_rate=round(blend["prior_rate"], 4),
        observed_rate=round(blend["observed_rate"], 4),
        alpha=round(blend["alpha"], 4),
        final_rate=round(blend["final_rate"], 4),
        safety_stock=_d(blend["safety_stock"]),
        min_stock=_d(blend["min_stock"]),
        max_stock=_d(blend["max_stock"]),
        recommended_quantity=_d(blend["recommended_quantity"]),
        window_start=dt.datetime.combine(blend["window_start"], dt.time.min),
        window_end=dt.datetime.combine(blend["window_end"], dt.time.min),
        n_sales=blend["n_sales"],
        source=blend["prior_source"],
        details=json.dumps(details, ensure_ascii=False),
    )
    session.add(log)
    await session.flush()
    logger.info(
        "recalc product=%s trigger=%s prior=%.3f obs=%.3f alpha=%.2f final=%.3f n=%d",
        product.id,
        trigger,
        blend["prior_rate"],
        blend["observed_rate"],
        blend["alpha"],
        blend["final_rate"],
        blend["n_sales"],
    )
    return log


async def recalc_market_products(trigger: str, market_id) -> None:
    """Recalculate every product of a market (used when market config changes)."""
    from app.database import SessionLocal

    async with SessionLocal() as session:
        result = await session.execute(
            select(Product).where(Product.market_id == market_id).options(selectinload(Product.category))
        )
        products = result.scalars().all()
        if not products:
            return
        market = await session.get(Market, market_id)
        for p in products:
            await recalc_product(session, p, market, trigger)
        await session.commit()