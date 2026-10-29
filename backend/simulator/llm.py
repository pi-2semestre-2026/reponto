"""LLM coach — the same OpenRouter setup used by the categorizer, applied to
game analysis. Given the run metrics, the model explains whether the
LightGBM-based recommender was accurate and what to tweak.

Fully optional: without OPENROUTER_API_KEY (or on any failure) a static
fallback report is returned, so the game never breaks.
"""

import logging

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger("simulator.llm")

VERDICT_LABEL = {
    "acertivo": "o recomendador foi acertivo",
    "parcial": "o recomendador foi razoável, com ressalvas",
    "fora": "o recomendador errou mais do que acertou",
    "sem_dados": "não houve dados suficientes",
}


def fallback_coach(report: dict) -> dict:
    s = report["summary"]
    v = report["verdict"]
    cats = report["per_category"]
    worst = cats[-1] if cats else None
    best = cats[0] if cats else None
    observations = []
    if s.get("wape_pct") is not None:
        observations.append(f"Erro médio (WAPE) de {s['wape_pct']}% entre o previsto e a demanda real.")
    if s.get("bias_pct") is not None:
        direction = "acima" if s["bias_pct"] > 0 else "abaixo"
        observations.append(f"Viés de {s['bias_pct']}%: o sistema comprou {direction} do necessário.")
    if s.get("service_pct") is not None:
        observations.append(f"Nível de serviço de {s['service_pct']}% dos dias sem ruptura de estoque.")
    recommendations = [
        "Compare o fator sazonal do modelo com os meses de pico e vale do relatório.",
        worst and f"Investigue a categoria {worst['category']} (WAPE {worst['wape_pct']}%) — pode haver padrão que o modelo não captura.",
        "Ajuste o ciclo de reposição ou o estoque de segurança se o viés persistir.",
    ]
    return {
        "verdict": v["level"],
        "headline": f"Análise local: {VERDICT_LABEL.get(v['level'], v['level'])}.",
        "observations": [o for o in observations if o],
        "recommendations": [r for r in recommendations if r],
        "source": "fallback",
    }


async def coach_report(report: dict) -> dict:
    if not settings.OPENROUTER_API_KEY:
        return fallback_coach(report)
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=settings.OPENROUTER_MODEL,
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            temperature=0.4,
            max_tokens=700,
            timeout=30,
            max_retries=1,
            extra_body={"reasoning": {"exclude": True}},
        )

        payload = {
            "config": report.get("config", {}),
            "summary": report["summary"],
            "verdict": report["verdict"],
            "per_category": report["per_category"][:8],
            "totals": report["totals"],
        }

        system = (
            "Você é o coach do 'Simulador de Estoque' do Reponto, um jogo que testa se o "
            "recomendador de compras (blend de um modelo LightGBM de sazonalidade com a taxa "
            "de vendas observada) acerta a demanda de um mercado.\n"
            "Recebe as métricas de uma partida simulada e avalia a QUALIDADE DAS PREVISÕES.\n"
            "Responda SOMENTE com JSON no formato:\n"
            '{"verdict": "acertivo" | "parcial" | "fora", '
            '"headline": "uma frase curta e divertida de resumo", '
            '"observations": ["2 a 3 observações objetivas sobre os números"], '
            '"recommendations": ["2 a 3 sugestões práticas de calibragem"]}\n'
            "Escreva em português do Brasil, tom de coach de jogo, direto ao ponto.\n"
            "WAPE é o erro percentual absoluto médio (menor é melhor). bias_pct positivo significa "
            "que o sistema comprou ACIMA da demanda real; negativo, abaixo. service_pct é o "
            "percentual de dias sem ruptura.\n\nMétricas da partida:\n"
        )

        import json

        response = await llm.ainvoke(
            [SystemMessage(content=system), HumanMessage(content=json.dumps(payload, ensure_ascii=False))]
        )
        text = response.content
        if not isinstance(text, str):
            text = ""
        import re

        text = re.sub(r"```(?:json)?", "", text).strip().strip("`")
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError("sem JSON na resposta")
        import json as _json

        data = _json.loads(match.group(0))
        data["source"] = "llm"
        return data
    except Exception:
        logger.exception("coach LLM falhou — usando fallback local")
        return fallback_coach(report)
