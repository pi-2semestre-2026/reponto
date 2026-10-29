"""Natural-language explanation of a recommendation — numbers first, words second.

Every number comes from the recommender (`compute_blend`). The LLM only turns
those numbers into a short text for the owner; it never decides anything.
A verifier then extracts every number the LLM wrote and checks it against the
computed facts. One unmatched number (or a missing purchase quantity) rejects
the text, and a deterministic template — consistent by construction — is shown
instead. The response says which of the two was used and what was checked.
"""

import logging
import math
import re
import time

from app.config import get_settings
from app.services import forecast_math as fm
from app.services.recommender import compute_blend

settings = get_settings()
logger = logging.getLogger("explainer")

REL_TOLERANCE = 0.04
ABS_TOLERANCE = 0.051
CACHE_MAX = 512
_cache: dict[tuple, dict] = {}

FORBIDDEN_JARGON = ("alpha", "alfa", "prior", "blend", "lightgbm", "taxa observada")


def fmt(value: float, places: int = 1) -> str:
    """PT-BR number: comma decimal, no trailing ',0'."""
    if value is None:
        return "—"
    text = f"{value:,.{places}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if "," in text:
        text = text.rstrip("0").rstrip(",")
    return text


UNIT_PLURAL = {"unidade": "unidades", "pacote": "pacotes", "caixa": "caixas", "dz": "dúzias"}


def unit_label(unit: str | None) -> str:
    u = (unit or "unidade").strip()
    return UNIT_PLURAL.get(u, u)


WEEKDAY_PLURAL = fm.WEEKDAY_PLURAL
MIN_PEAK_PCT = 10


def build_facts(product, market, blend: dict) -> dict:
    stock = float(product.stock or 0)
    rate = float(blend["final_rate"])
    cycle = int(blend["cycle"])
    recommended = float(blend["recommended_quantity"])
    buy = max(0, math.ceil(recommended - stock - 1e-9))
    coverage = stock / rate if rate > 0 and stock > 0 else None
    status = "esgotado" if stock <= 0 else ("abaixo do mínimo" if stock <= blend["min_stock"] else "ok")
    peak = fm.peak_summary(blend["weekday_index"])
    own_profile = blend["profile_source"] in ("produto", "loja") and peak["peak_pct"] >= MIN_PEAK_PCT
    return {
        "produto": product.name,
        "categoria": blend.get("category_name"),
        "unidade": unit_label(product.unit),
        "estoque_atual": round(stock, 1),
        "venda_por_dia": round(rate, 1),
        "ciclo_dias": cycle,
        "venda_no_ciclo": round(rate * cycle, 1),
        "estoque_minimo": round(blend["min_stock"], 1),
        "nivel_recomendado": round(recommended, 1),
        "estoque_maximo": round(blend["max_stock"], 1),
        "margem_seguranca": round(blend["safety_stock"], 1),
        "comprar": buy,
        "dias_cobertura": round(coverage, 1) if coverage is not None else None,
        "vendas_registradas": int(blend["n_sales"]),
        "peso_vendas_loja_pct": round(blend["alpha"] * 100),
        "peso_padrao_mercado_pct": round((1 - blend["alpha"]) * 100),
        "confianca": blend["confidence"],
        "situacao": status,
        "perfil_fonte": blend["profile_source"],
        "dia_pico": WEEKDAY_PLURAL[peak["peak_weekday"]] if own_profile else None,
        "pico_pct": peak["peak_pct"] if own_profile else None,
        "dias_reposicao": round(blend["reorder_days"], 1),
        "metodo_seguranca": blend["safety_method"],
        "erro_diario": round(blend["sigma_daily"], 1) if blend["sigma_daily"] is not None else None,
        "nivel_servico_pct": fm.SERVICE_LEVEL_PCT if blend["safety_method"] == "erro" else None,
    }


NUMERIC_FACTS = (
    ("estoque_atual", "estoque atual"),
    ("venda_por_dia", "venda por dia"),
    ("ciclo_dias", "ciclo de reposição"),
    ("venda_no_ciclo", "venda no ciclo"),
    ("estoque_minimo", "estoque mínimo"),
    ("nivel_recomendado", "nível recomendado"),
    ("estoque_maximo", "estoque máximo"),
    ("margem_seguranca", "margem de segurança"),
    ("comprar", "quantidade a comprar"),
    ("dias_cobertura", "dias de cobertura"),
    ("vendas_registradas", "vendas registradas"),
    ("peso_vendas_loja_pct", "peso das vendas da loja"),
    ("peso_padrao_mercado_pct", "peso do padrão de mercado"),
    ("pico_pct", "venda acima da média no dia forte"),
    ("dias_reposicao", "dias cobertos pelo mínimo"),
    ("erro_diario", "erro típico por dia"),
    ("nivel_servico_pct", "nível de serviço"),
)


def template_text(f: dict) -> str:
    u = f["unidade"]
    parts = []
    if f["situacao"] == "esgotado":
        parts.append(f"{f['produto']} está esgotado.")
    elif f["situacao"] == "abaixo do mínimo":
        parts.append(
            f"Atenção: {f['produto']} está com {fmt(f['estoque_atual'])} {u}, abaixo do mínimo de {fmt(f['estoque_minimo'])}."
        )
    elif f["dias_cobertura"] is not None:
        parts.append(
            f"O estoque atual de {fmt(f['estoque_atual'])} {u} de {f['produto']} dura cerca de {fmt(f['dias_cobertura'])} dias."
        )
    parts.append(
        f"A loja deve vender em torno de {fmt(f['venda_por_dia'])} {u} por dia, ou {fmt(f['venda_no_ciclo'])} no ciclo de {f['ciclo_dias']} dias."
    )
    if f["dia_pico"]:
        parts.append(
            f"Na sua loja, este produto vende {f['pico_pct']}% acima da média {f['dia_pico']}, "
            "e a previsão de cada dia já leva isso em conta."
        )
    if f["comprar"] > 0:
        parts.append(
            f"Recomendamos comprar {f['comprar']} {u} para chegar a {fmt(f['nivel_recomendado'])}, "
            f"o que cobre o ciclo com uma margem de segurança de {fmt(f['margem_seguranca'])}."
        )
    else:
        parts.append(f"Não precisa comprar agora: o estoque já está acima do nível recomendado de {fmt(f['nivel_recomendado'])}.")
    if f["metodo_seguranca"] == "erro" and f["erro_diario"] is not None:
        parts.append(
            f"Essa margem vem do erro típico da previsão, de {fmt(f['erro_diario'])} {u} por dia, "
            f"e protege contra falta em {f['nivel_servico_pct']}% dos ciclos."
        )
    n = f["vendas_registradas"]
    if n == 0:
        parts.append("Como ainda não há vendas registradas, a estimativa usa o padrão de mercados parecidos.")
    elif f["peso_vendas_loja_pct"] < 50:
        parts.append(
            f"A estimativa junta as {n} vendas da sua loja ({f['peso_vendas_loja_pct']}% do peso) com o padrão de mercados parecidos; "
            "com mais vendas, ela passa a seguir só a sua loja."
        )
    else:
        parts.append(f"A estimativa segue principalmente as {n} vendas da sua loja ({f['peso_vendas_loja_pct']}% do peso).")
    return " ".join(parts)


# ---------------------------------------------------------------- verification

NUMBER_RE = re.compile(r"(?<![\w])\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?")


def extract_numbers(text: str) -> list[tuple[str, float]]:
    found = []
    for raw in NUMBER_RE.findall(text):
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", raw):
            value = float(raw.replace(".", "").replace(",", "."))
        else:
            value = float(raw.replace(",", "."))
        found.append((raw, value))
    return found


def match_fact(value: float, facts: dict) -> str | None:
    """Closest computed fact within tolerance (71 is "comprar 71", not "nível 70,4")."""
    best, best_diff = None, None
    for key, label in NUMERIC_FACTS:
        v = facts.get(key)
        if v is None:
            continue
        diff = abs(value - v)
        if diff <= max(ABS_TOLERANCE, REL_TOLERANCE * abs(v)) and (best_diff is None or diff < best_diff):
            best, best_diff = label, diff
    return best


def verify(text: str, facts: dict) -> dict:
    checked, unmatched, values = [], [], []
    # Numbers that belong to the product name ("Água 500ml", "Arroz 5kg") are not claims.
    name_numbers = {v for _, v in extract_numbers(f"{facts['produto']} {facts.get('categoria') or ''}")}
    for raw, value in extract_numbers(text):
        if value in name_numbers:
            continue
        values.append(value)
        label = match_fact(value, facts)
        if label:
            checked.append({"value": raw, "fact": label})
        else:
            unmatched.append(raw)

    def mentions(*keys: str) -> bool:
        """Required facts are checked by value: two facts may share it (stock 0 -> buy == target)."""
        targets = [facts[k] for k in keys if facts.get(k) is not None]
        return any(abs(v - t) <= max(ABS_TOLERANCE, REL_TOLERANCE * abs(t)) for v in values for t in targets)

    problems = []
    if unmatched:
        problems.append(f"números que não existem no cálculo: {', '.join(unmatched)}")
    if facts["comprar"] > 0 and not mentions("comprar"):
        problems.append("não informou a quantidade a comprar")
    if not mentions("venda_por_dia", "venda_no_ciclo"):
        problems.append("não explicou o ritmo de venda")
    lowered = text.lower()
    jargon = [w for w in FORBIDDEN_JARGON if w in lowered]
    if jargon:
        problems.append(f"usou jargão técnico ({', '.join(jargon)})")
    return {"ok": not problems, "checked": checked, "problems": problems}


# ---------------------------------------------------------------- LLM


def facts_for_prompt(f: dict) -> str:
    u = f["unidade"]
    lines = [
        f"Produto: {f['produto']}" + (f" (categoria {f['categoria']})" if f.get("categoria") else ""),
        f"Situação do estoque: {f['situacao']}",
        f"Estoque atual: {fmt(f['estoque_atual'])} {u}",
        f"Venda estimada por dia: {fmt(f['venda_por_dia'])} {u}",
        f"Ciclo de reposição: {f['ciclo_dias']} dias",
        f"Venda estimada no ciclo: {fmt(f['venda_no_ciclo'])} {u}",
        f"Estoque mínimo (ponto de pedido): {fmt(f['estoque_minimo'])} {u}",
        f"Nível recomendado após a compra: {fmt(f['nivel_recomendado'])} {u}",
        f"Margem de segurança: {fmt(f['margem_seguranca'])} {u}",
        f"Quantidade a comprar agora: {f['comprar']} {u}",
    ]
    if f["dias_cobertura"] is not None:
        lines.append(f"O estoque atual dura: {fmt(f['dias_cobertura'])} dias")
    if f["dia_pico"]:
        lines.append(f"Dia em que este produto mais vende nesta loja: {f['dia_pico']} ({f['pico_pct']}% acima da média do dia)")
    if f["metodo_seguranca"] == "erro" and f["erro_diario"] is not None:
        lines.append(
            f"A margem de segurança vem do erro típico da previsão: {fmt(f['erro_diario'])} {u} por dia, "
            f"para não faltar em {f['nivel_servico_pct']}% dos ciclos"
        )
    lines += [
        f"Vendas da loja usadas no cálculo: {f['vendas_registradas']}",
        f"Peso das vendas da loja na estimativa: {f['peso_vendas_loja_pct']}%",
        f"Peso do padrão de mercados parecidos (dados públicos): {f['peso_padrao_mercado_pct']}%",
        f"Confiança: {f['confianca']}",
    ]
    return "\n".join(lines)


SYSTEM_PROMPT = (
    "Você explica recomendações de compra para o dono de um mercadinho de bairro, que não é analista.\n"
    "Os números já foram calculados pelo sistema. Sua tarefa é só explicar, em português do Brasil.\n"
    "Regras obrigatórias:\n"
    "- Use SOMENTE os números da lista, escritos exatamente como aparecem (vírgula como separador decimal).\n"
    "- Não faça contas, não arredonde de outro jeito e não invente números, datas ou porcentagens.\n"
    "- Diga quanto comprar (ou que não precisa comprar) e por quê: ritmo de venda e quantos dias o estoque dura.\n"
    "- Cite sempre a venda estimada por dia.\n"
    "- Se houver um dia em que o produto vende mais nesta loja, mencione isso.\n"
    "- Diga de onde vem a estimativa: vendas da própria loja e padrão de mercados parecidos.\n"
    "- 3 ou 4 frases curtas, tom direto e respeitoso, sem listas e sem markdown.\n"
    "- Não use as palavras alpha, prior, blend, LightGBM ou 'taxa observada'."
)


async def llm_text(facts: dict, feedback: list[str] | None = None) -> str | None:
    if not settings.OPENROUTER_API_KEY:
        return None
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        from app.services.categorizer import _response_text

        llm = ChatOpenAI(
            model=settings.OPENROUTER_MODEL,
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            temperature=0.2,
            max_tokens=1200,
            timeout=25,
            max_retries=1,
            # Writing a short text needs no hidden reasoning: off cuts ~20 s to ~3 s.
            extra_body={"reasoning": {"enabled": False}},
        )
        human = facts_for_prompt(facts)
        if feedback:
            human += "\n\nSua resposta anterior foi recusada pela conferência: " + "; ".join(feedback) + ". Corrija."
        response = await llm.ainvoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=human)])
        text = re.sub(r"[*_#`]", "", _response_text(response)).strip()
        return text or None
    except Exception:
        logger.exception("LLM explanation failed")
        return None


async def explain(session, product, market, last_log_id: int | None, refresh: bool = False) -> dict:
    key = (product.id, last_log_id, float(product.stock or 0))
    if not refresh and key in _cache:
        return _cache[key]

    blend = await compute_blend(session, product, market)
    facts = build_facts(product, market, blend)
    started = time.perf_counter()
    candidate = await llm_text(facts)
    result: dict
    if candidate:
        check = verify(candidate, facts)
        if not check["ok"]:
            # One corrective retry: tell the model what the check refused.
            retry = await llm_text(facts, feedback=check["problems"])
            if retry:
                retry_check = verify(retry, facts)
                if retry_check["ok"]:
                    candidate, check = retry, retry_check
        if check["ok"]:
            result = {"text": candidate, "source": "llm", "checked": check["checked"], "rejected": None}
        else:
            logger.warning("LLM explanation rejected for %s: %s", product.id, check["problems"])
            fallback = template_text(facts)
            result = {
                "text": fallback,
                "source": "template",
                "checked": verify(fallback, facts)["checked"],
                "rejected": {"text": candidate, "problems": check["problems"]},
            }
    else:
        fallback = template_text(facts)
        result = {"text": fallback, "source": "template", "checked": verify(fallback, facts)["checked"], "rejected": None}

    result["facts"] = facts
    result["llm_enabled"] = bool(settings.OPENROUTER_API_KEY)
    result["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
    if len(_cache) >= CACHE_MAX:
        _cache.pop(next(iter(_cache)))
    _cache[key] = result
    return result
