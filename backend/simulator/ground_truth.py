"""The DemandOracle — the simulator's independent "reality".

Deliberately built with a DIFFERENT functional form than the LightGBM
model (additive weekday/month tables + lognormal noise + discrete events,
vs LightGBM's learned trees). Correlated with reality in spirit, but with
its own patterns — so a high score from the recommender means real
predictive skill, not self-fulfilling prophecy.
"""

import datetime as dt
import math
import random

WEEKDAY_FACTOR = {0: 0.90, 1: 0.85, 2: 0.88, 3: 0.98, 4: 1.20, 5: 1.38, 6: 1.06}
MONTH_FACTOR = {
    1: 1.12, 2: 0.92, 3: 0.94, 4: 0.98, 5: 1.00, 6: 1.06,
    7: 1.04, 8: 0.97, 9: 1.00, 10: 1.03, 11: 1.06, 12: 1.30,
}
HOT_CATEGORIES = {"Bebidas", "Congelados e Frios", "Hortifrúti"}
FESTIVE_CATEGORIES = {"Bebidas", "Carnes e Aves", "Festa e Papelaria", "Padaria"}

EVENT_TYPES: dict[str, dict] = {
    "heatwave": {
        "emoji_kind": "heat",
        "duration_days": 2,
        "global_mult": 1.0,
        "category_mult": 1.55,
        "categories": HOT_CATEGORIES,
    },
    "holiday": {
        "emoji_kind": "party",
        "duration_days": 1,
        "global_mult": 1.45,
        "category_mult": 1.3,
        "categories": FESTIVE_CATEGORIES,
    },
    "rival_promo": {
        "emoji_kind": "down",
        "duration_days": 3,
        "global_mult": 0.72,
        "category_mult": 1.0,
        "categories": set(),
    },
    "street_fair": {
        "emoji_kind": "up",
        "duration_days": 1,
        "global_mult": 1.0,
        "category_mult": 1.7,
        "categories": {"Hortifrúti"},
    },
    "payday_week": {
        "emoji_kind": "up",
        "duration_days": 4,
        "global_mult": 1.18,
        "category_mult": 1.0,
        "categories": set(),
    },
}

EVENT_PROB_PER_DAY = 0.035
NOISE_SIGMA = 0.24


class DemandOracle:
    """Generates ground-truth daily demand and world events."""

    def __init__(self, catalog: list[dict], seed: int) -> None:
        self.rng = random.Random(seed)
        self.catalog = catalog
        self.active_events: list[dict] = []

    def _maybe_spawn_event(self, date: dt.date) -> None:
        if self.rng.random() > EVENT_PROB_PER_DAY:
            return
        kind = self.rng.choice(list(EVENT_TYPES.keys()))
        spec = EVENT_TYPES[kind]
        self.active_events.append(
            {
                "kind": kind,
                "starts_on": date,
                "ends_on": date + dt.timedelta(days=spec["duration_days"] - 1),
                "global_mult": spec["global_mult"],
                "category_mult": spec["category_mult"],
                "categories": set(spec["categories"]),
            }
        )

    def _expire_events(self, date: dt.date) -> None:
        self.active_events = [e for e in self.active_events if e["ends_on"] >= date]

    def events_on(self, date: dt.date) -> list[dict]:
        return [e for e in self.active_events if e["starts_on"] <= date <= e["ends_on"]]

    def event_multiplier(self, category: str, date: dt.date) -> float:
        mult = 1.0
        for e in self.events_on(date):
            mult *= e["global_mult"]
            if category in e["categories"]:
                mult *= e["category_mult"]
        return mult

    def base_rate(self, product: dict, customers_per_day: int) -> float:
        from app.services.seed_data import baseline_by_name

        return baseline_by_name(product["category"]) * product["strength"] * customers_per_day

    def demand_rate(self, product: dict, date: dt.date, customers_per_day: int) -> float:
        rate = self.base_rate(product, customers_per_day)
        rate *= WEEKDAY_FACTOR[date.weekday()]
        rate *= MONTH_FACTOR[date.month]
        rate *= self.event_multiplier(product["category"], date)
        return max(0.0, rate)

    def sample_demand(self, product: dict, date: dt.date, customers_per_day: int) -> int:
        """Poisson draw around a lognormal-shocked rate. This is the truth."""
        rate = self.demand_rate(product, date, customers_per_day)
        shocked = rate * math.exp(self.rng.gauss(0.0, NOISE_SIGMA))
        lam = max(0.0, shocked)
        if lam < 30:
            L = math.exp(-lam)
            k, p = 0, 1.0
            while True:
                p *= self.rng.random()
                if p <= L:
                    return k
                k += 1
        else:
            return max(0, int(self.rng.gauss(lam, math.sqrt(lam) + 0.5)))

    def step_day(self, date: dt.date) -> list[dict]:
        """Advance the world: spawn/expire events. Returns today's events."""
        self._expire_events(date)
        self._maybe_spawn_event(date)
        return [
            {
                "kind": e["kind"],
                "emoji_kind": EVENT_TYPES[e["kind"]]["emoji_kind"],
                "ends_on": e["ends_on"].isoformat(),
                "starts_on": e["starts_on"].isoformat(),
            }
            for e in self.events_on(date)
            if e["starts_on"] == date
        ]
