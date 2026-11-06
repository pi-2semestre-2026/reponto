"""Laboratório da banca: 3 meses de um mercado em ~1 minuto.

A demo built to be SHOWN: a small market whose "reality" is known and
editable, so anyone can watch the real Reponto brain learn it.

  - Cerveja: sells little on Tuesday and much more Friday to Sunday
    (delivery every 2 days).
  - Pão francês: sells every day, a bit more on Sunday; baked daily and
    leftovers are thrown away (perishable).
  - Leite: steady all week, restocked weekly (the control product).

Two twin stores face EXACTLY the same customers every day (same random
draws): one runs the real Reponto brain (simulator/brain.py — the same
weekday-profile learning, the same rule->model switch at 8 weeks and the
same calibrated safety margin as production); the other is an owner
without AI who restocks what he sold last week, ignoring the weekday.

Mid-demo the presenter can change reality ("jogo de futebol às quartas":
beer sales on Wednesday jump) and watch the AI adapt.

In memory only: nothing touches the database.
"""

import datetime as dt
import math
import random

from simulator.brain import SimRecommender

WEEKDAY_SHORT = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
DAYS = 91
CUSTOMERS_PER_DAY = 150
NOISE_SIGMA = 0.15
NOAI_MARGIN = 1.10
CHART_DAYS = 35

LAB_PRODUCTS = [
    {
        "key": "cerveja",
        "name": "Cerveja lata 350ml",
        "category": "Bebidas",
        "unit": "unidade",
        "base": 42.0,
        "pattern": [0.80, 0.50, 0.70, 0.90, 1.35, 1.95, 1.60],
        "cycle_days": 2,
        "price": 3.49,
        "cost": 2.40,
        "perishable": False,
        "story": "Vende pouco na terça e muito de sexta a domingo.",
    },
    {
        "key": "pao",
        "name": "Pão francês",
        "category": "Padaria",
        "unit": "unidade",
        "base": 260.0,
        "pattern": [1.00, 0.95, 0.95, 0.95, 1.00, 1.05, 1.20],
        "cycle_days": 1,
        "price": 0.80,
        "cost": 0.35,
        "perishable": True,
        "story": "Vende todo dia, um pouco mais no domingo. O que sobra no fim do dia vai fora.",
    },
    {
        "key": "leite",
        "name": "Leite integral 1L",
        "category": "Laticínios e Ovos",
        "unit": "unidade",
        "base": 28.0,
        "pattern": [1.0, 1.0, 1.0, 1.0, 1.0, 1.05, 0.95],
        "cycle_days": 7,
        "price": 5.49,
        "cost": 4.10,
        "perishable": False,
        "story": "Venda estável a semana toda (produto de controle).",
    },
]

SHIFTS = {
    "jogo_quarta": {
        "label": "Começou o campeonato: jogo toda quarta à noite",
        "product": "cerveja",
        "multipliers": {2: 2.6},
    },
    "normal": {"label": "Fim do campeonato: tudo volta ao normal", "product": "cerveja", "multipliers": {}},
}


def normalized(pattern: list[float]) -> list[float]:
    mean = sum(pattern) / 7
    return [v / mean for v in pattern]


def poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    if lam < 30:
        limit, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= rng.random()
            if p <= limit:
                return k
            k += 1
    return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))


class LabEngine:
    kind = "lab"

    def __init__(self, seed: int | None = None, days: int = DAYS) -> None:
        self.seed = seed if seed is not None else random.SystemRandom().randrange(1, 10**6)
        self.rng = random.Random(self.seed)
        self.total_days = days
        today = dt.date.today()
        this_monday = today - dt.timedelta(days=today.weekday())
        self.start_date = this_monday - dt.timedelta(weeks=math.ceil(days / 7))
        self.day_index = 0
        self.done = False
        self.shifts: list[dict] = []
        self.products = []
        for spec in LAB_PRODUCTS:
            p = dict(spec)
            p["true_pattern"] = list(spec["pattern"])
            p["brain"] = SimRecommender(CUSTOMERS_PER_DAY, spec["cycle_days"])
            start = round(spec["base"] * spec["cycle_days"] * 1.1)
            p["ai"] = {"stock": float(start), "history": {}, "rec": None, "sold_out": set()}
            p["noai"] = {"stock": float(start), "sales": {}}
            p["log"] = []
            p["pattern_error"] = []
            self.products.append(p)
        self.store_history: dict[dt.date, float] = {}
        self.cash = {
            "ai": {"revenue": 0.0, "cost": 0.0, "lost_r": 0.0, "waste_r": 0.0, "stock_value_sum": 0.0},
            "noai": {"revenue": 0.0, "cost": 0.0, "lost_r": 0.0, "waste_r": 0.0, "stock_value_sum": 0.0},
        }

    @property
    def current_date(self) -> dt.date:
        return self.start_date + dt.timedelta(days=self.day_index)

    # ------------------------------------------------------------ reality

    def true_index(self, p: dict) -> list[float]:
        return normalized(p["true_pattern"])

    def apply_shift(self, kind: str) -> dict:
        spec = SHIFTS.get(kind)
        if spec is None:
            raise ValueError("mudança desconhecida")
        p = next(x for x in self.products if x["key"] == spec["product"])
        pattern = list(p["pattern"])
        for wd, mult in spec["multipliers"].items():
            pattern[wd] *= mult
        p["true_pattern"] = pattern
        event = {"kind": kind, "label": spec["label"], "day": self.day_index, "date": self.current_date.isoformat(), "product": p["key"]}
        self.shifts.append(event)
        return event

    def demand(self, p: dict, date: dt.date) -> int:
        lam = p["base"] * p["true_pattern"][date.weekday()] * math.exp(self.rng.gauss(0.0, NOISE_SIGMA))
        return poisson(self.rng, lam)

    # ------------------------------------------------------------ policies

    def ai_recommend(self, p: dict, date: dt.date) -> dict:
        ai = p["ai"]
        rec = p["brain"].recommend(p, ai["history"], date, ai["stock"], self.store_history, ai["sold_out"])
        ai["rec"] = rec
        return rec

    def noai_target(self, p: dict, date: dt.date) -> float:
        """Owner without AI: last 7 days' average x cycle + 10%, same every weekday."""
        sales = p["noai"]["sales"]
        past = [sales.get(date - dt.timedelta(days=i), None) for i in range(1, 8)]
        known = [s for s in past if s is not None]
        if not known:
            return p["base"] * p["cycle_days"] * 1.1
        return (sum(known) / len(known)) * p["cycle_days"] * NOAI_MARGIN

    # ------------------------------------------------------------ loop

    def step(self) -> dict:
        if self.done:
            raise RuntimeError("demonstração já terminou")
        date = self.current_date
        wd = date.weekday()
        store_total = 0.0
        day = {"day_index": self.day_index, "date": date.isoformat(), "weekday": wd, "products": []}

        for p in self.products:
            rec = self.ai_recommend(p, date)
            restock = self.day_index % p["cycle_days"] == 0
            ai, noai = p["ai"], p["noai"]
            noai_target = self.noai_target(p, date)
            if restock:
                for store, target, cash in ((ai, rec["recommended_quantity"], self.cash["ai"]), (noai, noai_target, self.cash["noai"])):
                    buy = max(0, round(target - store["stock"]))
                    store["stock"] += buy
                    cash["cost"] += buy * p["cost"]

            demand = self.demand(p, date)
            ai_sold = min(demand, int(ai["stock"]))
            noai_sold = min(demand, int(noai["stock"]))
            ai["stock"] -= ai_sold
            noai["stock"] -= noai_sold
            if ai["stock"] <= 0:
                ai["sold_out"].add(date)
            if ai_sold > 0:
                prev = ai["history"].get(date, (0.0, 0))
                ai["history"][date] = (prev[0] + ai_sold, prev[1] + max(1, round(ai_sold / 2)))
            noai["sales"][date] = noai_sold
            store_total += ai_sold

            for key, store, sold in (("ai", ai, ai_sold), ("noai", noai, noai_sold)):
                c = self.cash[key]
                c["revenue"] += sold * p["price"]
                c["lost_r"] += (demand - sold) * p["price"]
                if p["perishable"] and store["stock"] > 0:
                    c["waste_r"] += store["stock"] * p["cost"]
                    store["stock"] = 0.0
                c["stock_value_sum"] += store["stock"] * p["cost"]

            index = rec["weekday_index"]
            ai_forecast = rec["final_rate"] * index[wd]
            noai_forecast = noai_target / (p["cycle_days"] * NOAI_MARGIN)
            truth = self.true_index(p)
            err = sum(abs(index[i] - truth[i]) for i in range(7)) / 7 * 100
            p["pattern_error"].append({"day": self.day_index, "error_pp": round(err, 1)})
            entry = {
                "day": self.day_index,
                "date": date.isoformat(),
                "weekday": wd,
                "label": WEEKDAY_SHORT[wd],
                "demand": demand,
                "ai_forecast": round(ai_forecast, 1),
                "noai_forecast": round(noai_forecast, 1),
                "ai_sold": ai_sold,
                "noai_sold": noai_sold,
                "ai_stockout": ai_sold < demand,
                "noai_stockout": noai_sold < demand,
                "ai_stock": round(ai["stock"], 1),
                "noai_stock": round(noai["stock"], 1),
                "source": rec.get("forecast_source", "regra"),
            }
            p["log"].append(entry)
            day["products"].append({"key": p["key"], "demand": demand, "ai_sold": ai_sold, "noai_sold": noai_sold})

        self.store_history[date] = store_total
        self.day_index += 1
        if self.day_index >= self.total_days:
            self.done = True
        return day

    # ------------------------------------------------------------ view

    @staticmethod
    def _wape(rows: list[dict], key: str) -> float | None:
        demand = sum(r["demand"] for r in rows)
        if not demand:
            return None
        return round(100 * sum(abs(r[key] - r["demand"]) for r in rows) / demand, 1)

    def _store_summary(self, key: str) -> dict:
        c = self.cash[key]
        demand = sum(r["demand"] for p in self.products for r in p["log"])
        sold = sum(r[f"{key}_sold"] for p in self.products for r in p["log"])
        days = max(1, self.day_index)
        return {
            "fill_pct": round(100 * sold / demand, 1) if demand else None,
            "stockout_days": sum(1 for p in self.products for r in p["log"] if r[f"{key}_stockout"]),
            "revenue": round(c["revenue"], 2),
            "cost": round(c["cost"], 2),
            "lost_r": round(c["lost_r"], 2),
            "waste_r": round(c["waste_r"], 2),
            "avg_stock_value": round(c["stock_value_sum"] / days, 2),
        }

    def snapshot(self) -> dict:
        products = []
        for p in self.products:
            rec = p["ai"]["rec"] or {}
            recent = p["log"][-28:]
            truth = self.true_index(p)
            learned = rec.get("weekday_index") or [1.0] * 7
            weeks = 0
            if rec.get("forecast_source") == "modelo":
                weeks = rec.get("model_weeks") or 0
            products.append(
                {
                    "key": p["key"],
                    "name": p["name"],
                    "category": p["category"],
                    "story": p["story"],
                    "cycle_days": p["cycle_days"],
                    "perishable": p["perishable"],
                    "labels": list(WEEKDAY_SHORT),
                    "true_index": [round(v, 3) for v in truth],
                    "learned_index": [round(v, 3) for v in learned],
                    "pattern_error_pp": p["pattern_error"][-1]["error_pp"] if p["pattern_error"] else None,
                    "pattern_error_series": p["pattern_error"],
                    "source": rec.get("forecast_source", "regra"),
                    "switched_day": next((r["day"] for r in p["log"] if r["source"] == "modelo"), None),
                    "model_weeks": weeks,
                    "final_rate": round(rec.get("final_rate", 0.0), 2),
                    "recommended": round(rec.get("recommended_quantity", 0.0), 1),
                    "confidence": rec.get("confidence", "baixa"),
                    "stock_ai": round(p["ai"]["stock"], 1),
                    "stock_noai": round(p["noai"]["stock"], 1),
                    "history": p["log"][-CHART_DAYS:],
                    "wape_ai_28": self._wape(recent, "ai_forecast"),
                    "wape_noai_28": self._wape(recent, "noai_forecast"),
                    "stockouts_ai": sum(1 for r in p["log"] if r["ai_stockout"]),
                    "stockouts_noai": sum(1 for r in p["log"] if r["noai_stockout"]),
                }
            )
        date = self.current_date
        return {
            "kind": "lab",
            "seed": self.seed,
            "day_index": self.day_index,
            "total_days": self.total_days,
            "date": date.isoformat(),
            "weekday": WEEKDAY_SHORT[date.weekday()],
            "done": self.done,
            "customers_per_day": CUSTOMERS_PER_DAY,
            "products": products,
            "stores": {"ai": self._store_summary("ai"), "noai": self._store_summary("noai")},
            "shifts": self.shifts,
            "available_shifts": [{"kind": k, "label": v["label"]} for k, v in SHIFTS.items()],
        }
