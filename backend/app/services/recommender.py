"""Recommendation engine — the heart of the system.

prior_rate    = baseline (typical SKU units/customer/day of the category)
                x month factor (LightGBM on the Store Item Demand dataset)
                x customers/day
                (fallback: static category prior x customers/day)
observed_rate = exponentially-decayed weighted average over the window
                starting at the FIRST sale (capped to OBS_WINDOW_DAYS):
                sum(qty x 2^(-age/half_life)) / sum(day weights)
alpha         = max(0.3, n_sales_in_window / (n + 10))
final_rate    = alpha x observed + (1 - alpha) x prior
levels        = day-by-day projection with the store's weekday profile and
                safety stock from the forecast error (see forecast_math)

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
from app.services import forecast_math as fm
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
    "import": "Importação do ERP",
    "purchase": "Compra recebida",
    "daily": "Atualização diária (dias da semana)",
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
    category in a physical mercado) x month factor from the dataset model
    x customers/day.

    The Store Item Demand dataset only shapes the SEASONALITY — the month
    level here and the weekday shape (used as the last-resort prior of the
    weekday profile, see forecast_math). The absolute level comes from the
    category baselines, since the dataset's items are not the user's SKUs.

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

    factor = fm.month_factor(rate_model, today.month, size, SEASONAL_FACTOR_BOUNDS)
    if factor is not None:
        ctx["seasonal_factor"] = round(factor, 3)
        return baseline * factor * market.customers_per_day, "model", ctx

    if cat is not None:
        row = await session.get(CategoryPrior, cat.id)
        if row is not None:
            return row.prior_rate * market.customers_per_day, "static", ctx

    return baseline * market.customers_per_day, "default", ctx


async def store_weekday_index(session, market: Market, start: dt.date, end: dt.date, dataset_prior: list[float]) -> tuple[list[float], int]:
    """Store rhythm: receipts per weekday of the whole market, shrunk to the dataset shape."""
    app_tz = bindparam("app_tz_store", LOCAL_TZ_NAME, literal_execute=True)
    day = func.date(func.timezone(app_tz, Sale.sold_at))
    rows = (
        await session.execute(
            select(day, func.count(Sale.id))
            .where(Sale.market_id == market.id, Sale.status == "completed", Sale.sold_at >= day_bounds(start, start)[0])
            .group_by(day)
        )
    ).all()
    totals = {(d if isinstance(d, dt.date) else dt.date.fromisoformat(str(d))): float(n) for d, n in rows}
    first = min(totals) if totals else end
    series = fm.daily_series(totals, max(first, start), end)
    if len(series) < fm.MIN_DAYS_FOR_PROFILE:
        return list(dataset_prior), len(series)
    return fm.weekday_profile(series, dataset_prior, fm.STORE_SHRINK_K), len(series)


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
    day_totals: dict[dt.date, float] = {}
    for qty, sold_at, sale_id in rows:
        sale_date = _local_date(sold_at)
        if sale_date < window_start or sale_date > today:
            continue
        age = (today - sale_date).days
        numerator += float(qty) * decay_weight(age, half_life)
        day_totals[sale_date] = day_totals.get(sale_date, 0.0) + float(qty)
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

    # Weekday profile: product -> store -> public dataset (closed days only).
    size = prior_ctx["size_bucket"]
    dataset_index = fm.dataset_weekday_prior(rate_model, today.month, size)
    yesterday = today - dt.timedelta(days=1)
    store_index, store_days = await store_weekday_index(session, market, window_start, yesterday, dataset_index)
    series = fm.daily_series(day_totals, window_start, yesterday)
    if len(series) >= fm.MIN_DAYS_FOR_PROFILE:
        weekday_index = fm.weekday_profile(series, store_index, fm.PRODUCT_SHRINK_K)
        profile_source = "produto"
    elif store_days >= fm.MIN_DAYS_FOR_PROFILE:
        weekday_index = list(store_index)
        profile_source = "loja"
    else:
        weekday_index = list(dataset_index)
        profile_source = "padrao"

    levels = fm.stock_levels(final_rate, weekday_index, today, cycle, series)
    if levels["safety_method"] == "regra":
        notes.append(f"Menos de {fm.MIN_DAYS_FOR_ERROR} dias de histórico: margem de segurança pela regra fixa (30% do ciclo)")

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
        "safety_stock": levels["safety_stock"],
        "safety_method": levels["safety_method"],
        "sigma_daily": levels["sigma_daily"],
        "min_stock": levels["min_stock"],
        "max_stock": levels["max_stock"],
        "recommended_quantity": levels["recommended_quantity"],
        "cycle_demand": levels["cycle_demand"],
        "reorder_demand": levels["reorder_demand"],
        "reorder_days": levels["reorder_days"],
        "projection": levels["projection"],
        "weekday_index": weekday_index,
        "store_weekday_index": store_index,
        "dataset_weekday_index": dataset_index,
        "profile_source": profile_source,
        "profile_days": len(series),
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


def profile_payload(blend: dict) -> dict:
    """Weekday profile + day-by-day projection, ready for the API/UI."""
    today = blend["window_end"]
    index = blend["weekday_index"]
    days = []
    for i, qty in enumerate(blend["projection"]):
        d = today + dt.timedelta(days=i)
        days.append({"date": d.isoformat(), "weekday": d.weekday(), "label": fm.WEEKDAY_SHORT[d.weekday()], "qty": round(qty, 2)})
    return {
        "source": blend["profile_source"],
        "days_observed": blend["profile_days"],
        "index": [round(v, 3) for v in index],
        "store_index": [round(v, 3) for v in blend["store_weekday_index"]],
        "labels": list(fm.WEEKDAY_SHORT),
        "next_days": days,
        "cycle_demand": round(blend["cycle_demand"], 2),
        "reorder_days": blend["reorder_days"],
        "reorder_demand": round(blend["reorder_demand"], 2),
        "safety_method": blend["safety_method"],
        "sigma_daily": round(blend["sigma_daily"], 3) if blend["sigma_daily"] is not None else None,
        "service_level_pct": fm.SERVICE_LEVEL_PCT,
        **fm.peak_summary(index),
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
        "metodo_seguranca": blend["safety_method"],
        "erro_diario": round(blend["sigma_daily"], 3) if blend["sigma_daily"] is not None else None,
        "perfil_semana": [round(v, 3) for v in blend["weekday_index"]],
        "fonte_perfil": blend["profile_source"],
        "demanda_ciclo": round(blend["cycle_demand"], 3),
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

async def recalc_products(product_ids, trigger: str) -> None:
    """Recalculate a set of products in a fresh session (background-safe)."""
    from app.database import SessionLocal

    ids = [pid for pid in set(product_ids) if pid is not None]
    if not ids:
        return
    async with SessionLocal() as session:
        result = await session.execute(
            select(Product)
            .where(Product.id.in_(ids))
            .options(selectinload(Product.category), selectinload(Product.market))
        )
        for p in result.scalars().all():
            await recalc_product(session, p, p.market, trigger)
        await session.commit()
