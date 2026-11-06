"""Gera e executa os notebooks 02 e 03 da Fase 1 (requer data/raw/favorita e o .venv).

Uso: python scripts/experimentos/gerar_notebooks_fase1.py
"""

import subprocess
import sys

import nbformat as nbf


def build(path, cells):
    nb = nbf.v4.new_notebook()
    nb["cells"] = [nbf.v4.new_markdown_cell(c[1].strip("\n")) if c[0] == "md" else nbf.v4.new_code_cell(c[1].strip("\n")) for c in cells]
    nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    nbf.write(nb, path)


SETUP = """
import matplotlib.pyplot as plt
import pandas as pd

plt.rcParams.update({"figure.figsize": (11, 4), "axes.grid": True, "grid.alpha": 0.3,
                     "axes.spines.top": False, "axes.spines.right": False})
pd.options.display.float_format = "{:,.2f}".format
"""

nb02 = [
    ("md", """
# 02 — Agregação semanal e recorte das séries

Etapas 2 e 3 da Fase 1 (`docs/PLANO_ML.md`). Toda a lógica está em `src/pipeline/weekly.py`; aqui se confere e se decide.

**Decisão de semana:** segunda a domingo, rotulada pela segunda-feira. Vendas são variável de fluxo: a semana é a **soma** dos dias.
"""),
    ("code", SETUP + """
from pipeline.config import SELECTED_SERIES
from pipeline.data import load_stores, load_train
from pipeline.weekly import complete_weeks, select_series, to_weekly

daily = load_train()
stores = load_stores()
weekly = to_weekly(daily)
first, last = complete_weeks(daily["date"])
print(f"semanas completas: {weekly.week_start.nunique()} ({first.date()} a {last.date()} + 6 dias)")
weekly.head()
"""),
    ("md", """
## 1. Conferências da Etapa 2

As mesmas que os testes em `tests/pipeline/test_weekly.py` automatizam:
- cada série tem 240 linhas, sem `NaN`;
- a soma semanal bate com a diária no mesmo intervalo;
- `n_days` é 7 em todas as semanas, exceto 6 nas quatro semanas de Natal (25/12 não tem linha).
"""),
    ("code", """
sizes = weekly.groupby(["store_nbr", "family"], observed=True).size()
inside = daily[(daily.date >= first) & (daily.date <= last + pd.Timedelta(days=6))]
short = sorted(weekly.loc[weekly.n_days != 7, "week_start"].dt.strftime("%Y-%m-%d").unique())
print("linhas por série:", sizes.unique(), "| NaN:", int(weekly[["sales", "n_days"]].isna().sum().sum()))
print(f"soma semanal {weekly.sales.sum():,.0f} × diária {inside.sales.sum():,.0f}")
print("semanas com 6 dias:", short)
"""),
    ("md", """
## 2. O que a agregação compra e o que custa

A semana elimina o padrão de dia da semana e boa parte dos zeros. Em troca, apaga o perfil dentro da semana, que a Fase 3 recupera.
"""),
    ("code", """
zeros_daily = (daily.sales == 0).mean()
zeros_weekly = (weekly.sales == 0).mean()
print(f"zeros: {zeros_daily:.1%} das linhas diárias × {zeros_weekly:.1%} das semanais")
ex = daily[(daily.store_nbr == 44) & (daily.family == "BEVERAGES") & (daily.date >= "2016-01-04") & (daily.date < "2016-04-04")]
exw = weekly[(weekly.store_nbr == 44) & (weekly.family == "BEVERAGES") & (weekly.week_start >= "2016-01-04") & (weekly.week_start < "2016-04-04")]
fig, ax = plt.subplots(1, 2, figsize=(12, 3.5))
ax[0].plot(ex.date, ex.sales); ax[0].set_title("Loja 44 · BEVERAGES — diário (ritmo da semana visível)")
ax[1].bar(exw.week_start, exw.sales, width=5); ax[1].set_title("Mesmo período — semanal (ritmo some)")
plt.tight_layout(); plt.show()
"""),
    ("md", """
## 3. Recorte (Etapa 3): critérios declarados antes de olhar qualquer erro

1. Histórico completo: vende desde jan/2013 e não tem semana zerada.
2. Diversidade: uma loja grande (44, Quito, tipo A) e uma pequena (54, El Carmen, tipo C); famílias perecíveis e não perecíveis, estáveis e voláteis.
3. Famílias com equivalente direto nas categorias do app (pensando na Fase 7).
"""),
    ("code", """
g = weekly.groupby(["store_nbr", "family"], observed=True).sales
summary = pd.DataFrame({"media_semanal": g.mean(), "cv": g.std() / g.mean(), "semanas_zeradas": g.apply(lambda s: int((s == 0).sum()))}).reset_index()
summary = summary.merge(stores[["store_nbr", "city", "type"]], on="store_nbr")
keys = pd.DataFrame(SELECTED_SERIES, columns=["store_nbr", "family"])
chosen = summary.merge(keys, on=["store_nbr", "family"])
print(f"séries sem semana zerada: {(summary.semanas_zeradas == 0).sum()} de {len(summary)}")
chosen.sort_values(["store_nbr", "family"])
"""),
    ("code", """
cand = summary[summary.family.isin(["PRODUCE", "HOME CARE"]) & summary.store_nbr.isin([44, 54])]
print("Evitadas (PRODUCE tem semanas zeradas por falha de registro; HOME CARE sem histórico completo):")
cand
"""),
    ("code", """
sel = select_series(weekly, SELECTED_SERIES)
assert len(sel) == len(SELECTED_SERIES) * 240
fig, axes = plt.subplots(2, 4, figsize=(15, 6), sharex=True)
for ax, (key, s) in zip(axes.flat, sel.groupby(["store_nbr", "family"], observed=True)):
    ax.plot(s.week_start, s.sales, lw=1); ax.set_title(f"{key[0]} · {key[1]}", fontsize=10)
plt.tight_layout(); plt.show()
print(f"recorte: {len(sel)} linhas = {len(SELECTED_SERIES)} séries × 240 semanas")
"""),
    ("md", """
**Viés de seleção (limitação declarada):** séries limpas e volumosas fazem o erro parecer menor do que seria no catálogo inteiro. Por isso o modelo do app (Fase 2) é avaliado em **todas** as 1.729 séries, por faixa de volume.
"""),
]

nb03 = [
    ("md", """
# 03 — Baseline de média móvel e protocolo de avaliação

Etapa 5 da Fase 1. Previsão da semana *t* = média das 4 semanas que terminam em *t − 1*
(`src/pipeline/baseline.py`). Teste = últimas 52 semanas, com origem móvel.
**k = 4 foi fixado antes**; k = 1, 8 e 13 aparecem só como sensibilidade.
"""),
    ("code", SETUP + """
from pipeline.baseline import moving_average_forecast
from pipeline.config import SELECTED_SERIES, SENSITIVITY_WINDOWS, MA_WINDOW
from pipeline.data import load_train
from pipeline.evaluation import evaluate, test_period
from pipeline.weekly import select_series, to_weekly

weekly = select_series(to_weekly(load_train()), SELECTED_SERIES)
weekly["forecast"] = moving_average_forecast(weekly, window=MA_WINDOW, horizon=1)
per_series, residuals = evaluate(weekly)
period = test_period(weekly)
print(f"teste: {period[0].date()} a {period[-1].date()} ({len(period)} semanas)")
per_series
"""),
    ("md", """
## 1. Como ler

- **MAE** está na unidade da série: não compara a loja 44 (68 mil/semana) com a 54 (1,3 mil).
- **MAPE** é percentual e comparável. Faz sentido tirar a média dele entre séries; a média do MAE seria dominada pelas séries grandes.
- **WAPE** e **viés** usam a mesma definição do simulador do app.
"""),
    ("code", """
print(f"MAPE médio das séries: {per_series.mape.mean():.2f}% | WAPE médio: {per_series.wape.mean():.2f}% | viés médio: {per_series.bias.mean():+.2f}%")
"""),
    ("md", """
## 2. Sensibilidade a k (só análise: escolher k no teste seria calibrar no teste)
"""),
    ("code", """
rows = []
for k in (1, MA_WINDOW, *[w for w in SENSITIVITY_WINDOWS if w != 1]):
    w = weekly.assign(forecast=moving_average_forecast(weekly, window=k, horizon=1))
    ps, _ = evaluate(w)
    rows.append({"k": k, "MAPE médio": ps.mape.mean(), "WAPE médio": ps.wape.mean()})
pd.DataFrame(rows).set_index("k")
"""),
    ("md", """
## 3. Real × previsto no período de teste
"""),
    ("code", """
fig, axes = plt.subplots(4, 2, figsize=(14, 11), sharex=True)
for ax, (key, s) in zip(axes.flat, weekly[weekly.week_start.isin(period)].groupby(["store_nbr", "family"], observed=True)):
    ax.plot(s.week_start, s.sales, label="real", lw=1.5)
    ax.plot(s.week_start, s.forecast, label="média móvel 4", lw=1.5, ls="--")
    ax.set_title(f"{key[0]} · {key[1]}", fontsize=10)
axes[0, 0].legend(); plt.tight_layout(); plt.show()
"""),
    ("md", """
## 4. Onde a média móvel erra

O esperado: os maiores erros perto do Natal e do Ano-Novo, porque a média móvel não sabe que dezembro é diferente e chega atrasada a qualquer mudança de nível.
"""),
    ("code", """
residuals["ape"] = (residuals.error.abs() / residuals.sales) * 100
by_week = residuals.groupby("week_start").ape.mean()
fig, ax = plt.subplots()
ax.bar(by_week.index, by_week.values, width=5)
ax.set_title("Erro percentual médio das 8 séries por semana de teste"); plt.show()
by_week.sort_values(ascending=False).head(5).to_frame("MAPE da semana (%)")
"""),
    ("md", """
**Conclusão:** a média móvel de 4 semanas erra em torno de 9% (MAPE) nessas 8 séries, e os piores momentos são as viradas de ano. Essa é a régua da Fase 2. No app, o modelo LightGBM foi comparado com essa mesma média móvel em todas as 1.729 séries do Favorita, por faixa de volume (página `/modelo`).
"""),
]

build("notebooks/02_agregacao_e_selecao.ipynb", nb02)
build("notebooks/03_baseline_media_movel.ipynb", nb03)
for nb in ("notebooks/02_agregacao_e_selecao.ipynb", "notebooks/03_baseline_media_movel.ipynb"):
    r = subprocess.run([sys.executable, "-m", "jupyter", "nbconvert", "--to", "notebook", "--execute", "--inplace", nb, "--ExecutePreprocessor.timeout=900"], capture_output=True, text=True)
    print(nb, "ok" if r.returncode == 0 else r.stderr[-1500:])
