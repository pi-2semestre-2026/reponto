"""Roda o laboratório da banca no terminal (sem servidor), para conferência.

Uso (raiz do repo, com o modelo semanal treinado em ML_MODEL_PATH):
  PYTHONPATH=backend DATASET_DIR=$PWD/datasets ML_MODEL_PATH=$PWD/backend/ml_data/model.txt \
    python scripts/experimentos/rodar_laboratorio.py [seed] [dia_da_mudanca]
"""
import logging
import sys
import time

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
print("modelo semanal carregado:", weekly_model.load())
from simulator.lab import LabEngine  # noqa: E402

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 7
shift_day = int(sys.argv[2]) if len(sys.argv) > 2 else 63
e = LabEngine(seed=seed)
t = time.time()
for d in range(e.total_days):
    if d == shift_day:
        e.apply_shift("jogo_quarta")
    e.step()
    if (d + 1) in (14, 28, 56, shift_day, shift_day + 14, e.total_days):
        s = e.snapshot()
        for p in s["products"]:
            print(f"dia {d + 1:2} {p['key']:7} {p['source']:6} erro_padrão={p['pattern_error_pp']:5}pp "
                  f"erro_prev_28d IA={p['wape_ai_28']} semIA={p['wape_noai_28']} rupturas IA={p['stockouts_ai']} semIA={p['stockouts_noai']}")
        beer = next(p for p in s["products"] if p["key"] == "cerveja")
        print("   cerveja real ", [round(v, 2) for v in beer["true_index"]])
        print("   cerveja IA   ", [round(v, 2) for v in beer["learned_index"]])
print(f"tempo {time.time() - t:.1f}s")
for k, v in s["stores"].items():
    print(k, v, "lucro", round(v["revenue"] - v["cost"], 2))
