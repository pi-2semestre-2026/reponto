"""A/B in the simulator: previous rule vs validated weekly model, same seeds."""
import logging, statistics, sys
import pandas as pd

logging.disable(logging.INFO)
from app.config import get_settings
from app.services.ml import rate_model
from app.services.weekly_model import weekly_model
from simulator.engine import SimulationEngine
from simulator.metrics import running_summary

prof = pd.read_csv("C:/Projetos/reponto/datasets/favorita/perfil_diario.csv")
rows = [{"family": r.category, "month": r.month, "weekday": r.weekday, "size_bucket": r.size_bucket, "avg_sales_per_tx": r.index} for r in prof.itertuples()]
rate_model.ensure(get_settings().ML_MODEL_PATH, rows)
assert weekly_model.load(), "weekly model missing"

SEEDS = [11, 23, 37]
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 364
out = []
for scenario in ("bairro", "medio", "grande"):
    for cycle in (7, 3):
        for seed in SEEDS:
            for use in (False, True):
                e = SimulationEngine(scenario_key=scenario, days=DAYS, cycle_days=cycle, seed=seed)
                e.brain.use_weekly_model = use
                while not e.done:
                    e.step()
                # skip the first 8 weeks (both paths identical while the model has no history)
                ev = [d for d in e.day_evals if d["date"] >= (e.start_date + pd.Timedelta(days=56)).isoformat()]
                demand = sum(d["actual_demand"] for d in ev)
                sold = sum(d["actual_sales"] for d in ev)
                stockout_days = sum(1 for d in ev if d["stockout"])
                s = running_summary(e)
                out.append({
                    "scenario": scenario, "cycle": cycle, "seed": seed, "model": "novo" if use else "anterior",
                    "fill_rate": 100 * sold / demand, "service_days": 100 * (1 - stockout_days / len(ev)),
                    "profit": e.revenue - e.purchase_cost, "lost_r": e.lost_revenue,
                    "end_stock_value": sum(e.state[p["key"]]["stock"] * p["cost"] for p in e.catalog),
                    "rate_wape": s["rate_wape_pct"],
                })
df = pd.DataFrame(out)
agg = df.groupby(["scenario", "cycle", "model"])[["fill_rate", "service_days", "profit", "lost_r", "end_stock_value", "rate_wape"]].mean().round(1)
print(agg.to_string())
print("\nGeral:")
print(df.groupby("model")[["fill_rate", "service_days", "profit", "lost_r", "end_stock_value", "rate_wape"]].mean().round(1).to_string())
