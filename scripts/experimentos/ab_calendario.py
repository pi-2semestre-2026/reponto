"""A/B do calendário comercial no laboratório: mesmo mercado, mesma demanda, com e sem as datas.

Uso (raiz do repo):
  PYTHONPATH=backend DATASET_DIR=$PWD/datasets ML_MODEL_PATH=$PWD/backend/ml_data/model.txt \
    python scripts/experimentos/ab_calendario.py [n_seeds]
"""
import logging
import sys

import pandas as pd

logging.disable(logging.INFO)
from app.config import get_settings  # noqa: E402
from app.services.ml import rate_model  # noqa: E402
from app.services.weekly_model import weekly_model  # noqa: E402

prof = pd.read_csv("datasets/favorita/perfil_diario.csv")
rate_model.ensure(get_settings().ML_MODEL_PATH, [
    {"family": r.category, "month": r.month, "weekday": r.weekday, "size_bucket": r.size_bucket, "avg_sales_per_tx": r.index}
    for r in prof.itertuples()
])
weekly_model.load()
from simulator.lab import LabEngine  # noqa: E402


def run(seed: int, calendar: bool) -> dict:
    e = LabEngine(seed=seed)
    for p in e.products:
        p["brain"].use_calendar = calendar
    for _ in range(e.total_days):
        e.step()
    s = e.snapshot()
    ev_rows = [r for p in e.products for r in p["log"] if r["events"]]
    ev_dem = sum(r["demand"] for r in ev_rows)
    st = s["stores"]["ai"]
    return {
        "seed": seed, "calendario": calendar,
        "atendimento_%": st["fill_pct"], "rupturas": st["stockout_days"],
        "perda_R$": st["lost_r"], "descarte_R$": st["waste_r"], "lucro_bruto_R$": st["gross_profit"], "estoque_medio_R$": st["avg_stock_value"],
        "erro_dias_de_data_%": round(100 * sum(abs(r["ai_forecast"] - r["demand"]) for r in ev_rows) / ev_dem, 1),
        "aprendido": {p["key"]: {c["event"]: (c["real"], c["learned"]) for c in pp["calendar"]}
                      for p, pp in zip(e.products, s["products"])},
    }


n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
rows = [run(seed, cal) for seed in range(1, n + 1) for cal in (False, True)]
df = pd.DataFrame(rows).drop(columns="aprendido")
print(df.groupby("calendario").mean(numeric_only=True).drop(columns="seed").round(1).to_string())
print("\nReal x aprendido (semente 1):")
for k, v in rows[1]["aprendido"].items():
    print(" ", k, {e: f"real {a:.2f} / IA {b:.2f}" for e, (a, b) in v.items()})
