"""Calendário comercial brasileiro: datas que mexem na venda e quanto mexem.

Três camadas, da mais geral para a mais específica:

1. DATAS (este módulo, puro): salário no 5º dia útil (sábado conta, como na CLT) e os
   2 dias seguintes; adiantamento no dia 20 (antecipado se cair em domingo/feriado) e o
   dia seguinte; VR/VA no dia configurado no mercado e os 2 seguintes; semana do Natal
   (18-23/12), véspera de Natal, Réveillon, Ano Novo, Carnaval (sáb-ter), Páscoa (qui-sáb),
   Dia das Mães e dos Pais (sex-dom do 2º domingo de maio/agosto), Black Friday (4ª sexta de
   novembro), feriados nacionais e suas vésperas.

2. EFEITO DE REFERÊNCIA por categoria, medido no Favorita com as datas equivalentes do
   Equador (datasets/favorita/eventos.csv, `python -m pipeline.eventos`). Só datas que
   melhoraram a previsão na validação têm efeito ≠ 1; as demais começam neutras.

3. EFEITO DA LOJA: para cada produto, a venda em dias de cada data ÷ a venda do mesmo dia
   da semana nas 4 semanas anteriores (o mesmo método da referência). Encolhido para a
   referência enquanto há poucas ocorrências:
       efeito = (n · observado + K · referência) / (n + K)
   Assim "quando o VR cai, esta loja vende 30% mais de mercearia" é aprendido sozinho.
   Dias com duas datas juntas (feriado no dia do salário) entram descontando o efeito da outra.

Na projeção diária, datas que o modelo semanal já enxerga (feriados e o fim de ano, pelo
atributo de feriado e pela semana do ano) só REDISTRIBUEM a venda dentro da semana; as
demais (salário, VR, Dia das Mães...) SOMAM por cima. No caminho por regra, todas somam.
"""

import datetime as dt
import logging
import math
import os
import statistics
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger("calendario")

K_PRIOR = 6.0
MAX_DAY_MULT = 3.0
LEARN_LOOKBACK_DAYS = 400

# key: (rótulo, nome do efeito de referência no Favorita, o modelo semanal já enxerga?)
EVENTS: dict[str, tuple[str, str | None, bool]] = {
    "salario": ("Salário (5º dia útil)", "pagamento", False),
    "adiantamento": ("Adiantamento (dia 20)", "pagamento", False),
    "vale": ("VR/VA na conta", "pagamento", False),
    "semana_natal": ("Semana do Natal", "semana_natal", True),
    "vespera_natal": ("Véspera de Natal", "vespera_natal", True),
    "natal": ("Natal (loja fechada ou quase)", "ano_novo", True),
    "reveillon": ("Réveillon", "reveillon", True),
    "ano_novo": ("Ano Novo", "ano_novo", True),
    "carnaval": ("Carnaval", "carnaval", True),
    "pascoa": ("Páscoa", "pascoa", True),
    "dia_das_maes": ("Dia das Mães", "dia_das_maes", False),
    "dia_dos_pais": ("Dia dos Pais", None, False),
    "black_friday": ("Black Friday", "black_friday", False),
    "feriado": ("Feriado", "feriado", True),
    "vespera_feriado": ("Véspera de feriado", "vespera_feriado", False),
}


# ---------------------------------------------------------------- datas


def _holidays(year: int) -> frozenset:
    from app.services.weekly_model import br_national_holidays

    return br_national_holidays(year)


def is_business_day(d: dt.date) -> bool:
    """Dia útil para salário (CLT): segunda a sábado, sem feriado nacional."""
    return d.weekday() < 6 and d not in _holidays(d.year)


def fifth_business_day(year: int, month: int) -> dt.date:
    d, count = dt.date(year, month, 1), 0
    while True:
        if is_business_day(d):
            count += 1
            if count == 5:
                return d
        d += dt.timedelta(days=1)


def _previous_business(d: dt.date) -> dt.date:
    while not is_business_day(d):
        d -= dt.timedelta(days=1)
    return d


def _next_business(d: dt.date) -> dt.date:
    while not is_business_day(d):
        d += dt.timedelta(days=1)
    return d


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(weekday - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


@lru_cache(maxsize=128)
def _month_events(year: int, month: int, vr_day: int) -> dict:
    out: dict[dt.date, set] = {}

    def add(day: dt.date, key: str, span: int = 1):
        for i in range(span):
            out.setdefault(day + dt.timedelta(days=i), set()).add(key)

    add(fifth_business_day(year, month), "salario", 3)
    add(_previous_business(dt.date(year, month, 20)), "adiantamento", 2)
    if vr_day:
        last = (dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1)).day
        add(_next_business(dt.date(year, month, min(vr_day, last))), "vale", 3)
    if month == 12:
        for day in range(18, 24):
            add(dt.date(year, 12, day), "semana_natal")
        add(dt.date(year, 12, 24), "vespera_natal")
        add(dt.date(year, 12, 25), "natal")
        add(dt.date(year, 12, 31), "reveillon")
    if month == 1:
        add(dt.date(year, 1, 1), "ano_novo")
    from app.services.weekly_model import easter

    e = easter(year)
    for key, first, span in (("carnaval", e - dt.timedelta(days=50), 4), ("pascoa", e - dt.timedelta(days=3), 3)):
        for i in range(span):
            day = first + dt.timedelta(days=i)
            if day.month == month:
                add(day, key)
    if month == 5:
        add(_nth_weekday(year, 5, 6, 2) - dt.timedelta(days=2), "dia_das_maes", 3)
    if month == 8:
        add(_nth_weekday(year, 8, 6, 2) - dt.timedelta(days=2), "dia_dos_pais", 3)
    if month == 11:
        add(_nth_weekday(year, 11, 4, 4), "black_friday")
    special = {"ano_novo", "natal", "vespera_natal", "reveillon", "carnaval", "pascoa"}
    for h in _holidays(year):
        if h.month == month and not (out.get(h, set()) & special):
            add(h, "feriado")
        before = h - dt.timedelta(days=1)
        if before.year == year and before.month == month and before not in _holidays(year) and not (out.get(before, set()) & special):
            add(before, "vespera_feriado")
    return out


def events_on(day: dt.date, vr_day: int = 0) -> set[str]:
    return set(_month_events(day.year, day.month, int(vr_day or 0)).get(day, set()))


# ---------------------------------------------------------------- efeito de referência


@lru_cache(maxsize=1)
def _reference_table() -> dict:
    path = Path(os.environ.get("DATASET_DIR", "/datasets")) / "favorita" / "eventos.csv"
    table: dict[tuple[str, str], tuple[float, bool]] = {}
    if not path.exists():
        logger.info("eventos.csv ausente: datas comerciais começam neutras")
        return table
    import csv

    with open(path, encoding="utf8") as f:
        for row in csv.DictReader(f):
            table[(row["event"], row["category"])] = (float(row["effect"]), row.get("adopted", "True") == "True")
    return table


def reference_effect(key: str, category: str | None) -> float:
    ref = EVENTS[key][1]
    if ref is None:
        return 1.0
    t = _reference_table()
    for cat in (category, "__all__"):
        hit = t.get((ref, cat))
        if hit is not None:
            return hit[0] if hit[1] else 1.0
    return 1.0


# ---------------------------------------------------------------- aprendizado na loja


def learn_effects(day_totals: dict, start: dt.date, end: dt.date, category: str | None, vr_day: int = 0) -> dict:
    """Efeito de cada data para ESTE produto nesta loja, encolhido para a referência.

    1ª passada: só dias com uma data (efeito puro). 2ª passada: dias com duas ou mais datas
    (ex.: feriado que cai no dia do salário) entram com a razão dividida pelo efeito já
    estimado das outras datas. Sem isso, um terço dos feriados do ano se perderia."""
    days = [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]
    flagged = {d: events_on(d, vr_day) for d in days}
    observations = []
    for d in days:
        evs = flagged[d]
        if not evs:
            continue
        base = [day_totals.get(d - dt.timedelta(weeks=w), 0.0) for w in range(1, 5)
                if not flagged.get(d - dt.timedelta(weeks=w)) and d - dt.timedelta(weeks=w) >= start]
        if len(base) < 2:
            continue
        expected = statistics.mean(base)
        if expected <= 0:
            continue
        observations.append((evs, min(5.0, day_totals.get(d, 0.0) / expected)))

    def combine(ratios: dict) -> dict:
        out = {}
        for key in EVENTS:
            ref = reference_effect(key, category)
            obs = ratios.get(key, [])
            n = len(obs)
            effect = (n * statistics.mean(obs) + K_PRIOR * ref) / (n + K_PRIOR) if n else ref
            out[key] = {
                "effect": effect,
                "reference": ref,
                "observed": statistics.mean(obs) if n else None,
                "n": n,
                "source": "loja" if n >= 3 or (n > 0 and ref == 1.0) else ("referencia" if ref != 1.0 else "neutro"),
            }
        return out

    single: dict[str, list[float]] = {}
    for evs, ratio in observations:
        if len(evs) == 1:
            single.setdefault(next(iter(evs)), []).append(ratio)
    first = combine(single)
    ratios: dict[str, list[float]] = {k: list(v) for k, v in single.items()}
    for evs, ratio in observations:
        if len(evs) < 2:
            continue
        for key in evs:
            others = math.prod(first[o]["effect"] for o in evs if o != key)
            if others > 0:
                ratios.setdefault(key, []).append(min(5.0, ratio / others))
    return combine(ratios)


# ---------------------------------------------------------------- multiplicador por dia


def day_multipliers(start: dt.date, days: int, effects: dict, vr_day: int = 0, model_path: bool = False) -> list[float]:
    """Multiplicador de cada dia da projeção.

    model_path=True: datas que o modelo semanal já enxerga só redistribuem dentro da semana
    (média 1 na semana seg-dom); as outras multiplicam."""

    def parts(d):
        known = extra = 1.0
        for key in events_on(d, vr_day):
            eff = effects.get(key, {}).get("effect", 1.0)
            if EVENTS[key][2]:
                known *= eff
            else:
                extra *= eff
        return known, extra

    out = []
    for i in range(days):
        d = start + dt.timedelta(days=i)
        known, extra = parts(d)
        if model_path:
            monday = d - dt.timedelta(days=d.weekday())
            week_known = [parts(monday + dt.timedelta(days=j))[0] for j in range(7)]
            mean_known = sum(week_known) / 7
            known = known / mean_known if mean_known > 0 else 1.0
        out.append(max(0.0, min(MAX_DAY_MULT, known * extra)))
    return out


def upcoming(start: dt.date, days: int, effects: dict, vr_day: int = 0) -> list[dict]:
    """Próximas datas (uma linha por data e evento), para a tela."""
    rows = []
    for i in range(days):
        d = start + dt.timedelta(days=i)
        for key in sorted(events_on(d, vr_day)):
            e = effects.get(key, {"effect": 1.0, "source": "neutro", "n": 0})
            rows.append({"date": d.isoformat(), "event": key, "label": EVENTS[key][0], "effect": round(e["effect"], 3),
                         "source": e["source"], "n": e["n"]})
    return rows
