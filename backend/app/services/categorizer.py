"""Product categorization: local keywords first (fast/free), LLM fallback.

The LLM classifies the product into the user's PT-BR categories using their
descriptions, and MAY create a brand-new PT-BR category when nothing fits.
SystemMessage/HumanMessage are used directly — no {} templates — so JSON
examples in the prompt are not interpreted as LangChain template variables.
"""

import asyncio
import json
import logging
import re
import unicodedata

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import Category, Market, Product, RecommendationLog
from app.services.seed_data import DEFAULT_CATEGORY_NAME

settings = get_settings()
logger = logging.getLogger("categorizer")


def normalize(text: str) -> str:
    text = text.lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"\s+", " ", text)
    return text


async def get_categories(session) -> list[Category]:
    result = await session.execute(select(Category).order_by(Category.is_seed.desc(), Category.name))
    return list(result.scalars().all())


def keyword_categorize(product_name: str, categories: list[Category]) -> Category | None:
    n = normalize(product_name)
    if not n:
        return None
    best: Category | None = None
    best_len = 0
    best_count = 0
    for cat in categories:
        matched = 0
        longest = 0
        for kw in cat.keywords.split(","):
            k = normalize(kw)
            if k and k in n:
                matched += 1
                longest = max(longest, len(k))
        if matched > 0:
            if cat.name == DEFAULT_CATEGORY_NAME and best is not None:
                continue
            if longest > best_len or (longest == best_len and matched > best_count):
                best = cat
                best_len = longest
                best_count = matched
    return best


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    text = re.sub(r"```(?:json)?", "", text).strip().strip("`")
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _response_text(response) -> str:
    content = response.content
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        joined = " ".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        ).strip()
        if joined:
            return joined
    reasoning = getattr(response, "additional_kwargs", {}).get("reasoning_content") or {}
    if isinstance(reasoning, str):
        return reasoning
    if isinstance(reasoning, dict):
        return reasoning.get("text", "")
    return ""


async def llm_categorize(product_name: str, categories: list[Category]) -> Category | None:
    """Ask the LLM to pick an existing category or propose a new PT-BR one."""
    if not settings.OPENROUTER_API_KEY:
        return None
    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=settings.OPENROUTER_MODEL,
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            temperature=0,
            max_tokens=900,
            timeout=30,
            max_retries=1,
            extra_body={"reasoning": {"exclude": True}},
        )
        cat_lines = "\n".join(f"- {c.name}: {c.description}" for c in categories)
        system = (
            "Você é um assistente de categorização de produtos de mercado/supermercado.\n"
            "Dado um produto, escolha a categoria mais adequada dentre as categorias existentes abaixo.\n"
            "Se NENHUMA categoria existente encaixar bem, você PODE criar uma nova categoria em português.\n"
            "Responda SOMENTE com um JSON, sem nenhum texto fora dele, no formato:\n"
            '{"categoria": "<nome de categoria existente>"}\n'
            "ou, se precisar criar uma nova:\n"
            '{"nova_categoria": {"nome": "<nome curto em português>", "descricao": "<descrição com exemplos de produtos>"}}\n\n'
            "Categorias existentes:\n" + cat_lines
        )
        human = f"Produto: {product_name}"
        response = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=human)])
        payload = _extract_json(_response_text(response))
        if not payload:
            logger.warning("LLM returned unparseable answer for %r", product_name)
            return None

        existing_by_norm = {normalize(c.name): c for c in categories}
        chosen_name = payload.get("categoria")
        if chosen_name:
            chosen = existing_by_norm.get(normalize(str(chosen_name)))
            if chosen:
                return chosen
            name = str(chosen_name).strip()[:80]
            if name:
                return Category(name=name, description="", keywords=normalize(name), is_seed=False)
        if payload.get("nova_categoria"):
            new = payload["nova_categoria"]
            name = str(new.get("nome", "")).strip()[:80]
            if not name:
                return None
            dup = existing_by_norm.get(normalize(name))
            if dup:
                return dup
            return Category(
                name=name,
                description=str(new.get("descricao", "")).strip()[:2000],
                keywords=normalize(name),
                is_seed=False,
            )
        return None
    except Exception:
        logger.exception("LLM categorization failed for %r", product_name)
        return None


async def resolve_category(product_name: str) -> tuple[Category, str]:
    """Full categorization flow: keywords -> LLM -> default. Returns (category, method)."""
    async with SessionLocal() as session:
        categories = await get_categories(session)
        default = next((c for c in categories if c.name == DEFAULT_CATEGORY_NAME), categories[0] if categories else None)

        hit = keyword_categorize(product_name, categories)
        if hit is not None:
            return hit, "keywords"

        by_llm = await llm_categorize(product_name, categories)
        if by_llm is not None:
            if by_llm.id is None:
                session.add(by_llm)
                await session.commit()
                await session.refresh(by_llm)
            return by_llm, "llm"

        return default, "default"


async def recover_stale_products(max_age_seconds: int = 180) -> int:
    """Reprocess products the background flow never finished.

    Two orphan shapes, both safe to reprocess (recalculation is idempotent and
    every calc is appended to the audit trail):
      1. status='processing' for too long — server died mid-task;
      2. status='ready' with ZERO recommendation logs — a fallback committed
         before any rate was ever computed.
    """
    import datetime as dt

    from sqlalchemy import func as sa_func

    from app.services.clock import now_local

    cutoff = now_local() - dt.timedelta(seconds=max_age_seconds)
    ids: set = set()
    async with SessionLocal() as session:
        stuck = (
            await session.execute(
                select(Product).where(Product.status == "processing", Product.created_at < cutoff)
            )
        ).scalars()
        ids.update(p.id for p in stuck)

        never_calculated = (
            await session.execute(
                select(Product.id)
                .outerjoin(RecommendationLog, RecommendationLog.product_id == Product.id)
                .where(Product.status == "ready")
                .group_by(Product.id)
                .having(sa_func.count(RecommendationLog.id) == 0)
            )
        ).scalars()
        ids.update(never_calculated)

    for pid in ids:
        logger.warning("recovering product %s (stuck processing or never calculated)", pid)
        asyncio.create_task(process_product_background(pid))
    return len(ids)


async def process_product_background(product_id) -> None:
    """Background task: categorize + first recommendation, then mark ready.

    Never raises to the caller: on any failure the product falls back to the
    default category and still becomes ready.
    """
    from app.services.recommender import recalc_product

    async with SessionLocal() as session:
        try:
            result = await session.execute(
                select(Product).where(Product.id == product_id)
            )
            product = result.scalar_one_or_none()
            if product is None:
                return

            category, method = await resolve_category(product.name)
            product.category_id = category.id
            product.status = "ready"

            market = await session.get(Market, product.market_id)
            if market is not None:
                await recalc_product(session, product, market, "product_created")
            await session.commit()
            logger.info("product %r categorized as %r via %s", product.name, category.name, method)
        except Exception:
            logger.exception("background processing failed for product %s", product_id)
            try:
                await session.rollback()
                result = await session.execute(select(Product).where(Product.id == product_id))
                product = result.scalar_one_or_none()
                if product is not None:
                    if product.category_id is None:
                        categories = await get_categories(session)
                        default = next(
                            (c for c in categories if c.name == DEFAULT_CATEGORY_NAME), None
                        )
                        if default:
                            product.category_id = default.id
                            product.category = default
                    product.status = "ready"
                    try:
                        market = await session.get(Market, product.market_id)
                        if market is not None:
                            await recalc_product(session, product, market, "recalc")
                    except Exception:
                        logger.exception("fallback recalc failed for product %s", product_id)
                    await session.commit()
            except Exception:
                logger.exception("fallback finalize also failed for product %s", product_id)