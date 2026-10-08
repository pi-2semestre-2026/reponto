"""The day-loop game engine. Pure in-memory, zero DB writes.

Each simulated day, in order:
  1. the world (oracle) may spawn/expire demand events;
  2. on restock days the "obedient owner" buys exactly what the real math
     (brain) recommends, at cost price;
  3. ground-truth demand realizes; stock sells down to zero — the excess
     is LOST SALES the system never sees (it only sees what was sold);
  4. sales are recorded into the brain's history, mirroring what the
     recommender would learn in production.
"""

import datetime as dt
import random

from simulator.brain import SimRecommender
from simulator.ground_truth import DemandOracle
from simulator.metrics import running_summary
from simulator.scenarios import SCENARIOS, build_catalog

MIN_DAYS = 7
MAX_DAYS = 1095


class SimulationEngine:
    def __init__(self, scenario_key: str, days: int, cycle_days: int = 7, seed: int | None = None) -> None:
        scenario = SCENARIOS.get(scenario_key)
        if scenario is None:
            raise ValueError("cenário inválido")
        self.scenario_key = scenario.key
        self.scenario_name = scenario.name
        self.customers_per_day = scenario.customers_per_day
        self.total_days = max(MIN_DAYS, min(MAX_DAYS, int(days)))
        self.cycle_days = max(1, min(30, int(cycle_days)))
        self.seed = seed if seed is not None else random.SystemRandom().randrange(1, 10**6)

        self.rng = random.Random(self.seed)
        self.catalog = build_catalog(scenario, self.rng)
        self.oracle = DemandOracle(self.catalog, self.seed)
        self.brain = SimRecommender(self.customers_per_day, self.cycle_days)

        today = dt.date.today()
        self.start_date = dt.date(max(2020, today.year - 1), 1, 1)

        self.day_index = 0
        self.done = False
        self.revenue = 0.0
        self.purchase_cost = 0.0
        self.lost_revenue = 0.0

        self.state: dict[str, dict] = {
            p["key"]: {"stock": 0.0, "history": {}, "rec": None, "restocked_today": 0}
            for p in self.catalog
        }
        self._seed_shelves()

        self.daily_series: list[dict] = []
        self.event_log: list[dict] = []
        self.day_evals: list[dict] = []

    def _seed_shelves(self) -> None:
        """The owner opens the market with a stocked shelf — like the real
        onboarding flow, where a product is created with initial stock.
        Owner intuition = category-typical pace (no oracle info)."""
        for p in self.catalog:
            prior, _, _ = self.brain.prior_rate(p["category"], self.start_date)
            self.state[p["key"]]["stock"] = round(2.0 * self.cycle_days * prior, 1)

    @property
    def current_date(self) -> dt.date:
        return self.start_date + dt.timedelta(days=self.day_index)

    def _is_restock_day(self) -> bool:
        return self.day_index % self.cycle_days == 0

    def _restock(self, date: dt.date) -> dict[str, int]:
        """Top the shelf up TO the recommended level (a real owner doesn't
        stack `recommended_quantity` on top of leftovers)."""
        buys: dict[str, int] = {}
        for p in self.catalog:
            st = self.state[p["key"]]
            rec = self.brain.recommend(p, st["history"], date, st["stock"])
            st["rec"] = rec
            buy = max(0, round(rec["recommended_quantity"] - st["stock"]))
            st["stock"] += buy
            st["restocked_today"] = buy
            buys[p["key"]] = buy
            self.purchase_cost += buy * p["cost"]
        return buys

    def step(self) -> dict:
        """Advance exactly one day and return its report."""
        if self.done:
            raise RuntimeError("simulação já terminou")

        date = self.current_date
        new_events = self.oracle.step_day(date)
        for e in new_events:
            self.event_log.append({**e, "day": self.day_index, "date": date.isoformat()})

        buys: dict[str, int] = {}
        if self._is_restock_day():
            buys = self._restock(date)
        else:
            for st in self.state.values():
                st["restocked_today"] = 0

        day_revenue = 0.0
        day_cost = 0.0
        day_lost_r = 0.0
        day_sold = 0
        day_lost = 0
        day_demand = 0
        stockouts: list[str] = []
        product_deltas = []

        for p in self.catalog:
            st = self.state[p["key"]]
            demand = self.oracle.sample_demand(p, date, self.customers_per_day)
            sold = min(demand, int(st["stock"]))
            lost = demand - sold
            st["stock"] = max(0.0, st["stock"] - sold)
            if sold > 0:
                n_tx = max(1, round(sold / p["ups"]))
                prev = st["history"].get(date, (0.0, 0))
                st["history"][date] = (prev[0] + sold, prev[1] + n_tx)

            buy = buys.get(p["key"], 0)
            day_revenue += sold * p["price"]
            day_cost += buy * p["cost"]
            day_lost_r += lost * p["price"]
            day_sold += sold
            day_lost += lost
            day_demand += demand

            rec = st["rec"] or {}
            self.day_evals.append(
                {
                    "key": p["key"],
                    "date": date.isoformat(),
                    "category": p["category"],
                    "predicted": rec.get("final_rate", 0.0),
                    "actual_demand": demand,
                    "actual_sales": sold,
                    "stockout": lost > 0,
                    "initial": self.day_index == 0,
                }
            )
            if lost > 0:
                stockouts.append(p["name"])
                self.lost_revenue += lost * p["price"]
            product_deltas.append(
                {
                    "key": p["key"],
                    "sold": sold,
                    "lost": lost,
                    "demand": demand,
                    "restocked": buy,
                    "stock": st["stock"],
                }
            )

        self.revenue += day_revenue

        report = {
            "day_index": self.day_index,
            "date": date.isoformat(),
            "weekday": date.weekday(),
            "events": new_events,
            "restocked": [p["name"] for p in self.catalog if buys.get(p["key"], 0) > 0],
            "stockouts": stockouts,
            "revenue": round(day_revenue, 2),
            "cost": round(day_cost, 2),
            "lost_r": round(day_lost_r, 2),
            "sold_units": day_sold,
            "lost_units": day_lost,
            "demand_units": day_demand,
            "product_deltas": product_deltas,
        }
        self.daily_series.append(report)

        self.day_index += 1
        if self.day_index >= self.total_days:
            self.done = True
        return report

    def snapshot(self) -> dict:
        products = []
        last_deltas = (
            {d["key"]: d for d in self.daily_series[-1]["product_deltas"]}
            if self.daily_series
            else {}
        )
        for p in self.catalog:
            st = self.state[p["key"]]
            rec = st["rec"] or {}
            delta = last_deltas.get(p["key"], {})
            products.append(
                {
                    "key": p["key"],
                    "name": p["name"],
                    "category": p["category"],
                    "price": p["price"],
                    "cost": p["cost"],
                    "stock": round(st["stock"], 1),
                    "max_stock": round(rec.get("max_stock", 0.0), 1),
                    "min_stock": round(rec.get("min_stock", 0.0), 1),
                    "final_rate": round(rec.get("final_rate", 0.0), 3),
                    "confidence": rec.get("confidence", "baixa"),
                    "seasonal_factor": rec.get("seasonal_factor"),
                    "today_sold": delta.get("sold", 0),
                    "today_lost": delta.get("lost", 0),
                    "restocked": st["restocked_today"],
                }
            )

        return {
            "day_index": self.day_index,
            "total_days": self.total_days,
            "date": self.current_date.isoformat(),
            "done": self.done,
            "scenario": {
                "key": self.scenario_key,
                "name": self.scenario_name,
                "customers_per_day": self.customers_per_day,
                "cycle_days": self.cycle_days,
                "seed": self.seed,
            },
            "cash": {
                "revenue": round(self.revenue, 2),
                "cost": round(self.purchase_cost, 2),
                "profit": round(self.revenue - self.purchase_cost, 2),
                "lost_r": round(self.lost_revenue, 2),
                "stock_value": round(
                    sum(
                        self.state[p["key"]]["stock"] * p["cost"]
                        for p in self.catalog
                    ),
                    2,
                ),
            },
            "products": products,
            "summary": running_summary(self),
            "last_events": self.event_log[-3:],
        }
