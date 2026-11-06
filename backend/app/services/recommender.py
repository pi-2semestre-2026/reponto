"""Recommendation engine — the heart of the system.

Two forecasting paths, chosen per product:

1. Weekly model (products with >= 8 complete weeks of sales): the LightGBM
   validated in evaluation.py on 1.729 real supermarket series forecasts next
   week from the product's own weekly history; safety stock comes from its
   calibrated 95% upper bound (app.services.weekly_model).

2. Rule (new products, or before the model is trained):
   prior_rate    = baseline (typical SKU units/customer/day of the category)
                   x month factor (seasonal LightGBM, per category)
                   x customers/day
                   (fallback: static category prior x customers/day)
   observed_rate = exponentially-decayed weighted average over the window
                   starting at the FIRST sale (capped to OBS_WINDOW_DAYS):
                   sum(qty x 2^(-age/half_life)) / sum(day weights)
   alpha         = max(0.3, n_sales_in_window / (n + 10))
   final_rate    = alpha x observed + (1 - alpha) x prior

In both paths the daily projection uses the store's own weekday profile
(product -> store -> dataset, see forecast_math).

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
from app.services import weekly_model as wm
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
    "daily": "Atualização diária (dias da semana / modelo novo)",
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

    factor = fm.month_factor(rate_model, today.month, size, SEASONAL_FACTOR_BOUNDS, category=cat_name)
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


async def product_day_totals(session, product_id, start: dt.date, end: dt.date) -> dict[dt.date, float]:
    """Units sold per local day in [start, end] (completed sales only)."""
    app_tz = bindparam("app_tz_days", LOCAL_TZ_NAME, literal_execute=True)
    day = func.date(func.timezone(app_tz, Sale.sold_at))
    rows = (
        await session.execute(
            select(day, func.sum(SaleItem.quantity))
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(
                SaleItem.product_id == product_id,
                Sale.status == "completed",
                Sale.sold_at >= day_bounds(start, start)[0],
                Sale.sold_at < day_bounds(end, end)[1],
            )
            .group_by(day)
        )
    ).all()
    return {(d if isinstance(d, dt.date) else dt.date.fromisoformat(str(d))): float(q or 0) for d, q in rows}


async def stockout_days(session, product_id, start: dt.date) -> set[dt.date]:
    """Days on which a sale emptied the shelf (recorded in the audit log as estoque <= 0)."""
    rows = (
        await session.execute(
            select(RecommendationLog.created_at, RecommendationLog.details).where(
                RecommendationLog.product_id == product_id,
                RecommendationLog.trigger == "sale",
                RecommendationLog.created_at >= day_bounds(start, start)[0],
            )
        )
    ).all()
    days = set()
    for created_at, details in rows:
        try:
            stock = json.loads(details or "{}").get("estoque")
        except ValueError:
            continue
        if stock is not None and float(stock) <= 0:
            days.add(_local_date(created_at))
    return days


async def weekly_forecast(session, product: Product, first_sale: dt.date | None, today: dt.date, category: str | None, size: int, sold_out: set | None = None) -> dict | None:
    """Validated weekly model for this product, or None (rule-based path)."""
    if first_sale is None or not wm.weekly_model.ready:
        return None
    target_monday = today - dt.timedelta(days=today.weekday())
    start = max(first_sale, target_monday - dt.timedelta(weeks=wm.MAX_HISTORY_WEEKS))
    totals = await product_day_totals(session, product.id, start, target_monday - dt.timedelta(days=1))
    totals = {d: fm.uncensor(q, d in (sold_out or set())) for d, q in totals.items()}
    weeks = wm.weekly_history(totals, first_sale, target_monday)
    return wm.weekly_model.forecast(weeks, target_monday, category, size)


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

    sold_out = await stockout_days(session, product.id, min(window_start, today - dt.timedelta(weeks=wm.MAX_HISTORY_WEEKS)))
    n_sales = 0
    seen_sales: set = set()
    day_totals: dict[dt.date, float] = {}
    for qty, sold_at, sale_id in rows:
        sale_date = _local_date(sold_at)
        if sale_date < window_start or sale_date > today:
            continue
        day_totals[sale_date] = day_totals.get(sale_date, 0.0) + float(qty)
        if sale_id not in seen_sales:
            seen_sales.add(sale_id)
            n_sales += 1
    day_totals = {d: fm.uncensor(q, d in sold_out) for d, q in day_totals.items()}
    numerator = sum(q * decay_weight((today - d).days, half_life) for d, q in day_totals.items())

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

    # Weekday profile: product's own (recent weeks weigh more) shrunk towards
    # its category pattern adjusted to the store's rhythm (see forecast_math).
    size = prior_ctx["size_bucket"]
    category_index = fm.dataset_weekday_prior(rate_model, today.month, size, prior_ctx["category_name"])
    typical_index = fm.dataset_weekday_prior(rate_model, today.month, size, None)
    yesterday = today - dt.timedelta(days=1)
    store_start = today - dt.timedelta(days=obs_window)
    store_index, store_days = await store_weekday_index(session, market, store_start, yesterday, typical_index)
    product_prior = fm.category_store_prior(category_index, store_index, typical_index)
    series = fm.daily_series(day_totals, window_start, yesterday)
    if len(series) >= fm.MIN_DAYS_FOR_PROFILE:
        weekday_index = fm.weekday_profile(series, product_prior, fm.PRODUCT_SHRINK_K)
        profile_source = "produto"
    elif store_days >= fm.MIN_DAYS_FOR_PROFILE:
        weekday_index = list(product_prior)
        profile_source = "loja"
    else:
        weekday_index = list(category_index)
        profile_source = "padrao"

    service = fm.service_target(prior_ctx["category_name"], cycle, float(product.price or 0), float(product.cost or 0))

    first_local = None
    if first_sale_date is not None:
        first_local = first_sale_date if isinstance(first_sale_date, dt.date) else _local_date(first_sale_date)
    forecast = await weekly_forecast(session, product, first_local, today, prior_ctx["category_name"], size, sold_out)
    if sold_out:
        notes.append(f"{len(sold_out)} dia(s) em que o produto esgotou: a procura real foi estimada {round(fm.STOCKOUT_UPLIFT * 100)}% acima da venda registrada")

    if forecast is not None:
        forecast_source = "modelo"
        final_rate = forecast["weekly"] / 7.0
        levels = fm.model_stock_levels(final_rate, weekday_index, today, cycle, forecast, series, service["level"])
        confidence = "alta" if forecast["weeks"] >= 12 else "media"
        notes.append(
            f"Previsão do modelo semanal validado, a partir de {forecast['weeks']} semanas de vendas deste produto; "
            f"margem calibrada em dados reais para {round(service['level'] * 100)}% de atendimento (faixa {forecast['tier']} un/semana)"
        )
    else:
        forecast_source = "regra"
        levels = fm.stock_levels(final_rate, weekday_index, today, cycle, series, service["level"])
        if levels["safety_method"] == "regra":
            notes.append(f"Menos de {fm.MIN_DAYS_FOR_ERROR} dias de histórico: margem de segurança pela regra fixa (30% do ciclo)")
        confidence = "baixa" if n_sales < 3 else ("media" if n_sales < 10 else "alta")
        if first_local is not None and wm.weekly_model.ready:
            notes.append(f"Menos de {wm.MIN_WEEKS} semanas completas de vendas: estimativa pela regra (padrão da categoria + vendas recentes)")

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
        "forecast_source": forecast_source,
        "service_level": service["level"],
        "perishable": service["perishable"],
        "shelf_life_days": service["shelf_life_days"],
        "service_rule": service["rule"],
        "weekly_forecast": forecast["weekly"] if forecast else None,
        "weekly_upper": forecast["upper"] if forecast else None,
        "model_weeks": forecast["weeks"] if forecast else None,
        "model_tier": forecast["tier"] if forecast else None,
        "model_q95": forecast["q95"] if forecast else None,
        "model_has_last_year": forecast["has_last_year"] if forecast else None,
        "model_holiday_days": forecast["holiday_days"] if forecast else None,
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
        "category_weekday_index": category_index,
        "dataset_weekday_index": category_index,
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
        "category_index": [round(v, 3) for v in blend["category_weekday_index"]],
        "labels": list(fm.WEEKDAY_SHORT),
        "next_days": days,
        "cycle_demand": round(blend["cycle_demand"], 2),
        "reorder_days": blend["reorder_days"],
        "reorder_demand": round(blend["reorder_demand"], 2),
        "safety_method": blend["safety_method"],
        "sigma_daily": round(blend["sigma_daily"], 3) if blend["sigma_daily"] is not None else None,
        "service_level_pct": round(blend["service_level"] * 100),
        "perishable": blend["perishable"],
        "service_rule": blend["service_rule"],
        **fm.peak_summary(index),
    }


def _d(value: float, places: int = 3) -> Decimal:
    return Decimal(str(round(max(0.0, value), places)))


def formula_string(blend: dict) -> str:
    if blend.get("forecast_source") == "modelo":
        return (
            f"final = previsão do modelo semanal ({blend['weekly_forecast']:.2f}/sem) ÷ 7 = {blend['final_rate']:.3f}/d · "
            f"limite 95% = {blend['weekly_upper']:.2f}/sem"
        )
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
        "estoque": float(product.stock or 0),
        "seguranca": round(blend["safety_stock"], 3),
        "metodo_seguranca": blend["safety_method"],
        "erro_diario": round(blend["sigma_daily"], 3) if blend["sigma_daily"] is not None else None,
        "perfil_semana": [round(v, 3) for v in blend["weekday_index"]],
        "fonte_perfil": blend["profile_source"],
        "demanda_ciclo": round(blend["cycle_demand"], 3),
        "fonte_previsao": blend["forecast_source"],
        "previsao_semanal": round(blend["weekly_forecast"], 3) if blend["weekly_forecast"] is not None else None,
        "limite_95_semanal": round(blend["weekly_upper"], 3) if blend["weekly_upper"] is not None else None,
        "semanas_historico": blend["model_weeks"],
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
        source="modelo_semanal" if blend["forecast_source"] == "modelo" else blend["prior_source"],
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


async def refresh_stale_products(session, market: Market, products: list[Product]) -> int:
    """Recalculate products whose last calculation is from a previous day (the
    weekday projection moved) or older than the current weekly model (so they
    switch to it as soon as it is trained). Returns how many were refreshed."""
    if not products:
        return 0
    last_calc = dict(
        (
            await session.execute(
                select(RecommendationLog.product_id, func.max(RecommendationLog.created_at))
                .where(RecommendationLog.product_id.in_([p.id for p in products]))
                .group_by(RecommendationLog.product_id)
            )
        ).all()
    )
    model_time = None
    generated = wm.weekly_model.meta.get("generated_at") if wm.weekly_model.ready else None
    if generated:
        try:
            model_time = dt.datetime.fromisoformat(generated)
        except ValueError:
            model_time = None
    today = today_local()
    stale = [
        p
        for p in products
        if p.status == "ready"
        and (
            last_calc.get(p.id) is None
            or local_date(last_calc[p.id]) < today
            or (model_time is not None and last_calc[p.id] < model_time)
        )
    ]
    for p in stale:
        await recalc_product(session, p, market, "daily")
    return len(stale)


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
