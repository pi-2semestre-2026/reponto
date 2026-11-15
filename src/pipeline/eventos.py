"""Efeito de datas comerciais na venda, medido no Favorita: `python -m pipeline.eventos`.

Para cada categoria do app e cada tipo de data (pagamento, Natal, Carnaval, Dia das Mães...),
quanto a venda do dia fica acima (ou abaixo) do "dia normal" equivalente:

    efeito = venda do dia / média do mesmo dia da semana nas 4 semanas antes e 4 depois,
             sem contar outros dias de evento

A venda é somada por categoria entre todas as lojas abertas (série mais estável), e o efeito de
cada evento é a mediana das ocorrências. Datas do Equador usadas como análogas das brasileiras:
  pagamento        dias 15 e último do mês (setor público) e os 2 dias seguintes
  semana_natal     18 a 23/12          vespera_natal  24/12
  reveillon        31/12               ano_novo       01/01 (lojas fechadas ou quase)
  carnaval         sábado a terça      pascoa         quinta a sábado da Semana Santa
  dia_das_maes     sexta a domingo do 2º domingo de maio (igual ao Brasil)
  black_friday     a sexta da Black Friday (2014-2016)
  feriado          outros feriados nacionais      vespera_feriado  véspera deles

Validação: efeitos calculados só com datas ANTES do ano de teste; no ano de teste, a previsão
"dia normal" (média do mesmo dia da semana nas 4 semanas anteriores) é comparada com a mesma
previsão × efeito, nos dias de evento. Grava datasets/favorita/eventos.csv e
reports/eventos_validacao.csv.
"""

import numpy as np
import pandas as pd

from pipeline.app_export import EXPORT_DIR, FAMILY_TO_CATEGORY, national_holidays
from pipeline.config import REPORTS_DIR
from pipeline.data import load_holidays, load_train

TEST_START = pd.Timestamp("2016-08-15")
ALL = "__all__"
MIN_OCCURRENCES = 3


def event_days(holidays: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict[str, set]:
    days = pd.date_range(start, end)
    ev: dict[str, set] = {k: set() for k in (
        "pagamento", "semana_natal", "vespera_natal", "reveillon", "ano_novo", "carnaval",
        "pascoa", "dia_das_maes", "black_friday", "feriado", "vespera_feriado")}
    for d in days:
        last = (d + pd.offsets.MonthEnd(0)).day
        if d.day in (15, last):
            for k in range(3):
                ev["pagamento"].add(d + pd.Timedelta(days=k))
        if d.month == 12 and 18 <= d.day <= 23:
            ev["semana_natal"].add(d)
        if d.month == 12 and d.day == 24:
            ev["vespera_natal"].add(d)
        if d.month == 12 and d.day == 31:
            ev["reveillon"].add(d)
        if d.month == 1 and d.day == 1:
            ev["ano_novo"].add(d)
    nat = holidays[holidays["locale"] == "National"]
    for _, r in nat.iterrows():
        d, desc = r["date"], str(r["description"])
        if desc == "Carnaval":
            ev["carnaval"].update({d - pd.Timedelta(days=k) for k in range(0, 3)} | {d})
        elif desc == "Viernes Santo":
            ev["pascoa"].update({d - pd.Timedelta(days=1), d, d + pd.Timedelta(days=1)})
        elif desc == "Dia de la Madre":
            ev["dia_das_maes"].update({d - pd.Timedelta(days=2), d - pd.Timedelta(days=1), d})
        elif desc == "Black Friday":
            ev["black_friday"].add(d)
    special = set().union(*(ev[k] for k in ev if k not in ("pagamento",)))
    for d in national_holidays(holidays):
        if d not in special:
            ev["feriado"].add(d)
            ev["vespera_feriado"].add(d - pd.Timedelta(days=1))
    return {k: {d for d in v if start <= d <= end} for k, v in ev.items()}


def category_daily(daily: pd.DataFrame) -> pd.DataFrame:
    """Venda diária por categoria (soma das lojas), só lojas abertas desde jan/2013."""
    late = {20, 21, 22, 29, 36, 42, 52, 53}
    d = daily[~daily["store_nbr"].isin(late)].copy()
    d["category"] = d["family"].astype(str).map(FAMILY_TO_CATEGORY)
    by_cat = d.groupby(["category", "date"])["sales"].sum().reset_index()
    total = d.groupby("date")["sales"].sum().reset_index().assign(category=ALL)
    return pd.concat([by_cat, total], ignore_index=True)


def baseline(series: pd.Series, flagged: pd.Series, causal: bool) -> pd.Series:
    """Média do mesmo dia da semana nas semanas vizinhas (sem dias de evento).
    causal=True usa só as 4 semanas anteriores (o que se saberia no dia)."""
    s = series.where(~flagged)
    lags = [-7, -14, -21, -28] if causal else [-7, -14, -21, -28, 7, 14, 21, 28]
    shifted = pd.concat([s.shift(-lag, freq="D").reindex(s.index) for lag in lags], axis=1)
    return shifted.mean(axis=1, skipna=True)


def main() -> None:
    daily = load_train()
    holidays = load_holidays()
    cat = category_daily(daily)
    start, end = cat["date"].min(), cat["date"].max()
    ev = event_days(holidays, start, end)
    any_event = set().union(*ev.values())

    effects, validation = [], []
    for category, g in cat.groupby("category"):
        s = g.set_index("date")["sales"].asfreq("D")
        flagged = pd.Series(s.index.isin(list(any_event)), index=s.index)
        base_all = baseline(s, flagged, causal=False)
        base_causal = baseline(s, flagged, causal=True)
        ratio = s / base_all
        for name, days in ev.items():
            idx = [d for d in days if d in ratio.index and np.isfinite(ratio.get(d, np.nan)) and base_all.get(d, 0) > 0]
            train = [d for d in idx if d < TEST_START]
            test = [d for d in idx if d >= TEST_START]
            if len(train) < MIN_OCCURRENCES:
                continue
            effect_train = float(np.median(ratio.loc[train]))
            effect_all = float(np.median(ratio.loc[idx]))
            effects.append({"event": name, "category": category, "effect": round(effect_all, 4), "n": len(idx)})
            test = [d for d in test if base_causal.get(d, 0) > 0 and np.isfinite(base_causal.get(d, np.nan))]
            if test:
                y, b = s.loc[test].to_numpy(), base_causal.loc[test].to_numpy()
                validation.append({
                    "event": name, "category": category, "test_days": len(test), "effect_train": round(effect_train, 3),
                    "abs_err_without": float(np.abs(b - y).sum()), "abs_err_with": float(np.abs(b * effect_train - y).sum()),
                    "sales": float(y.sum()),
                })

    eff = pd.DataFrame(effects).sort_values(["event", "category"])
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    eff.to_csv(EXPORT_DIR / "eventos.csv", index=False)

    val = pd.DataFrame(validation)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    val.to_csv(REPORTS_DIR / "eventos_validacao.csv", index=False)
    by_event = val[val["category"] != ALL].groupby("event")[["abs_err_without", "abs_err_with", "sales", "test_days"]].sum()
    by_event["WAPE sem efeito %"] = 100 * by_event["abs_err_without"] / by_event["sales"]
    by_event["WAPE com efeito %"] = 100 * by_event["abs_err_with"] / by_event["sales"]
    tot = by_event[["abs_err_without", "abs_err_with", "sales"]].sum()
    print("Efeito (todas as categorias):")
    print(eff[eff["category"] == ALL].set_index("event")[["effect", "n"]].to_string())
    print("\nValidação no ano de teste (dias de evento, por categoria somadas):")
    print(by_event[["test_days", "WAPE sem efeito %", "WAPE com efeito %"]].round(1).to_string())
    print(f"\nTOTAL: sem efeito {100 * tot.abs_err_without / tot.sales:.1f}% | com efeito {100 * tot.abs_err_with / tot.sales:.1f}%")


if __name__ == "__main__":
    main()
