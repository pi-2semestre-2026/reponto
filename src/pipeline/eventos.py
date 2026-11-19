"""Efeito de datas comerciais na venda, medido no Favorita: `python -m pipeline.eventos`.

Para cada categoria do app e cada tipo de data (pagamento, Natal, Carnaval, Dia das Mães...),
quanto a venda do dia fica acima (ou abaixo) do "dia normal" equivalente:

    efeito = venda do dia / média do mesmo dia da semana nas 4 semanas ANTERIORES,
             sem contar outros dias de evento

(Só as semanas anteriores: é o que o app conhece no momento de prever. A primeira versão usava
também as semanas seguintes e inflava o efeito do fim de ano, porque janeiro é fraco.)

A venda é somada por categoria entre todas as lojas abertas (série mais estável), e o efeito de
cada evento é a mediana das ocorrências. Datas do Equador usadas como análogas das brasileiras:
  pagamento        dias 15 e último do mês (setor público) e os 2 dias seguintes
  semana_natal     18 a 23/12          vespera_natal  24/12
  reveillon        31/12               ano_novo       01/01 (lojas fechadas ou quase)
  carnaval         sábado a terça      pascoa         quinta a sábado da Semana Santa
  dia_das_maes     sexta a domingo do 2º domingo de maio (igual ao Brasil)
  black_friday     a sexta da Black Friday (2014-2016)
  feriado          outros feriados nacionais      vespera_feriado  véspera deles

Escolha sem olhar o teste (mesmo protocolo do modelo semanal):
  1. efeito medido com as datas até ago/2015;
  2. ano de VALIDAÇÃO (ago/2015-ago/2016): a data é ADOTADA se a previsão "dia normal x efeito"
     erra menos que a previsão "dia normal" nos dias dessa data (somando as categorias);
  3. ano de TESTE (ago/2016-ago/2017): só confirma o resultado das datas adotadas.
Datas não adotadas entram com efeito 1,0 (o app aprende o efeito com as vendas da própria loja).
O efeito exportado das datas adotadas usa todas as ocorrências. Grava datasets/favorita/eventos.csv
e reports/eventos_validacao.csv.
"""

import numpy as np
import pandas as pd

from pipeline.app_export import EXPORT_DIR, FAMILY_TO_CATEGORY, national_holidays
from pipeline.config import REPORTS_DIR
from pipeline.data import load_holidays, load_train

VAL_START = pd.Timestamp("2015-08-17")
TEST_START = pd.Timestamp("2016-08-15")
ALL = "__all__"
MIN_OCCURRENCES = 2  # datas anuais de um dia (Natal, Ano Novo) têm 2 ocorrências no treino


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

    rows = []
    for category, g in cat.groupby("category"):
        s_ = g.set_index("date")["sales"].asfreq("D")
        flagged = pd.Series(s_.index.isin(list(any_event)), index=s_.index)
        base = baseline(s_, flagged, causal=True)
        ok = (base > 0) & np.isfinite(base) & s_.notna()
        for name, days in ev.items():
            for d in days:
                if d in ok.index and ok.loc[d]:
                    period = "treino" if d < VAL_START else ("validacao" if d < TEST_START else "teste")
                    rows.append({"event": name, "category": category, "date": d, "period": period,
                                 "sales": float(s_.loc[d]), "base": float(base.loc[d])})
    obs = pd.DataFrame(rows)
    obs["ratio"] = obs["sales"] / obs["base"]

    def effect_from(frame):
        return frame.groupby(["event", "category"])["ratio"].agg(["median", "size"]).reset_index()

    def score(frame, effects):
        f = frame.merge(effects, on=["event", "category"], how="inner")
        f = f[f["category"] != ALL]
        out = f.assign(e0=(f["base"] - f["sales"]).abs(), e1=(f["base"] * f["median"] - f["sales"]).abs())
        return out.groupby("event")[["e0", "e1", "sales"]].sum().assign(dias=out.groupby("event").size())

    train_eff = effect_from(obs[obs["period"] == "treino"])
    train_eff = train_eff[train_eff["size"] >= MIN_OCCURRENCES]
    val = score(obs[obs["period"] == "validacao"], train_eff)
    adopted = sorted(val.index[val["e1"] < val["e0"]])

    trainval_eff = effect_from(obs[obs["period"] != "teste"])
    test = score(obs[obs["period"] == "teste"], trainval_eff)

    report = pd.DataFrame({
        "dias_validacao": val["dias"],
        "WAPE_validacao_sem_%": 100 * val["e0"] / val["sales"],
        "WAPE_validacao_com_%": 100 * val["e1"] / val["sales"],
        "adotado": [e in adopted for e in val.index],
    }).join(pd.DataFrame({
        "dias_teste": test["dias"],
        "WAPE_teste_sem_%": 100 * test["e0"] / test["sales"],
        "WAPE_teste_com_%": 100 * test["e1"] / test["sales"],
    }), how="left")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report.round(2).to_csv(REPORTS_DIR / "eventos_validacao.csv")

    final = effect_from(obs).rename(columns={"median": "effect", "size": "n"})
    final["adopted"] = final["event"].isin(adopted)
    final.loc[~final["adopted"], "effect"] = 1.0
    final["effect"] = final["effect"].round(4)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    final.sort_values(["event", "category"]).to_csv(EXPORT_DIR / "eventos.csv", index=False)

    print("Escolha na validação e confirmação no teste (WAPE nos dias de cada data, %):")
    print(report.round(1).to_string())
    a = test.loc[[e for e in adopted if e in test.index and e != "ano_novo"]]
    print(f"\nTeste, datas adotadas (sem Ano Novo, que sem efeito erra ~100x a venda do dia): "
          f"sem efeito {100 * a.e0.sum() / a.sales.sum():.1f}% | com efeito {100 * a.e1.sum() / a.sales.sum():.1f}%")
    print("\nEfeito exportado (todas as categorias):")
    print(final[final["category"] == ALL].set_index("event")[["effect", "n", "adopted"]].to_string())


if __name__ == "__main__":
    main()
