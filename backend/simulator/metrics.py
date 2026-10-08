"""Forecast-accuracy metrics — the whole point of the game.

Compares, per product-day, the rate the REAL math predicted (final_rate in
effect that day) against the ground-truth demand that realized. Lost sales
are tracked separately: they show how often the recommendation left the
shelf empty (the system only learns from what it managed to sell).
"""

import datetime as dt

import statistics


def _forecast_errors(engine) -> list[dict]:
    return [
        {
            "key": e["key"],
            "category": e["category"],
            "date": e["date"],
            "predicted": e["predicted"],
            "actual": e["actual_demand"],
            "stockout": e["stockout"],
            "initial": e.get("initial", False),
        }
        for e in engine.day_evals
    ]


def _aggregate(errors: list[dict]) -> dict:
    if not errors:
        return {"mae": None, "wape_pct": None, "bias_pct": None, "samples": 0}
    actual_total = sum(e["actual"] for e in errors)
    abs_err = sum(abs(e["predicted"] - e["actual"]) for e in errors)
    bias = sum(e["predicted"] - e["actual"] for e in errors)
    return {
        "mae": round(abs_err / len(errors), 3),
        "wape_pct": round(100 * abs_err / actual_total, 1) if actual_total else None,
        "bias_pct": round(100 * bias / actual_total, 1) if actual_total else None,
        "samples": len(errors),
    }


def rate_wape(engine, errors: list[dict] | None = None) -> float | None:
    """WAPE of the RATE estimate, aggregated per product-week.

    Daily WAPE has a statistical floor from Poisson noise on slow SKUs;
    summing predicted rate × 7 vs actual demand per week is the honest
    measure of whether the recommender estimates the pace correctly.
    """
    errors = errors if errors is not None else _forecast_errors(engine)
    weeks: dict[tuple, dict] = {}
    for e in errors:
        iso = dt.date.fromisoformat(e["date"]).isocalendar()
        week_key = (e["key"], iso[0], iso[1])
        agg = weeks.setdefault(week_key, {"predicted": 0.0, "actual": 0})
        agg["predicted"] += e["predicted"]
        agg["actual"] += e["actual"]
    abs_err = sum(abs(w["predicted"] - w["actual"]) for w in weeks.values())
    actual_total = sum(w["actual"] for w in weeks.values())
    return round(100 * abs_err / actual_total, 1) if actual_total else None


def running_summary(engine) -> dict:
    """Lightweight metrics for the HUD (cheap enough per step).

    `clean_*` metrics exclude product-days with stockouts (and the cold-start
    day), where lost sales hide real demand — they measure the MODEL's skill;
    the overall ones measure the operation as the player lived it.
    """
    errors = _forecast_errors(engine)
    if not errors:
        return {
            "mae": None, "wape_pct": None, "bias_pct": None,
            "service_pct": None, "samples": 0,
            "wape_clean_pct": None, "bias_clean_pct": None,
            "rate_wape_pct": None,
        }
    base = _aggregate(errors)
    stockouts = sum(1 for e in errors if e["stockout"])
    clean = _aggregate([e for e in errors if not e["stockout"] and not e["initial"]])
    return {
        **base,
        "service_pct": round(100 * (len(errors) - stockouts) / len(errors), 1),
        "wape_clean_pct": clean["wape_pct"],
        "bias_clean_pct": clean["bias_pct"],
        "rate_wape_pct": rate_wape(engine, [e for e in errors if not e["initial"]]),
    }


def verdict(summary: dict, cash: dict) -> dict:
    """Qualitative verdict on whether the recommender is trustworthy.

    Judged on the weekly rate WAPE (model skill), the clean bias and the
    service level — isolating the model from operating noise."""
    wape = summary.get("rate_wape_pct") or summary.get("wape_clean_pct") or summary.get("wape_pct")
    bias = summary.get("bias_clean_pct") or summary.get("bias_pct")
    service = summary.get("service_pct")
    if wape is None:
        return {"level": "sem_dados", "direction": None, "score": None}

    score = 0
    if wape <= 15:
        score += 2
    elif wape <= 30:
        score += 1
    if bias is not None and abs(bias) <= 10:
        score += 1
    if service is not None and service >= 97:
        score += 1

    if score >= 4:
        level = "acertivo"
    elif score >= 2:
        level = "parcial"
    else:
        level = "fora"

    direction = None
    if bias is not None and abs(bias) > 10:
        direction = "superestima" if bias > 0 else "subestima"
    return {
        "level": level,
        "direction": direction,
        "score": score,
        "waste_r": round(cash.get("lost_r", 0.0), 2),
    }


def full_report(engine) -> dict:
    errors = _forecast_errors(engine)
    summary = running_summary(engine)
    clean_overall = _aggregate([e for e in errors if not e["stockout"] and not e["initial"]])

    by_cat: dict[str, dict] = {}
    for e in errors:
        agg = by_cat.setdefault(
            e["category"],
            {"category": e["category"], "errors": [], "clean": [], "n": 0, "stockouts": 0},
        )
        agg["errors"].append(e)
        agg["n"] += 1
        if e["stockout"]:
            agg["stockouts"] += 1
        elif not e["initial"]:
            agg["clean"].append(e)
    per_category = []
    for agg in by_cat.values():
        overall = _aggregate(agg["errors"])
        clean = _aggregate(agg["clean"])
        per_category.append(
            {
                "category": agg["category"],
                "mae": overall["mae"],
                "wape_pct": overall["wape_pct"],
                "bias_pct": overall["bias_pct"],
                "wape_clean_pct": clean["wape_pct"],
                "bias_clean_pct": clean["bias_pct"],
                "rate_wape_pct": rate_wape(engine, agg["clean"]),
                "stockout_pct": round(100 * agg["stockouts"] / agg["n"], 1),
                "samples": agg["n"],
            }
        )
    per_category.sort(key=lambda c: c["rate_wape_pct"] if c["rate_wape_pct"] is not None else 999)

    weekly: dict[str, dict] = {}
    for e in errors:
        week = e["date"][:7] + "-W" + e["date"][8:10]
        key = e["date"][:10]
        wk = weekly.setdefault(key, {"predicted": 0.0, "actual": 0})
        wk["predicted"] += e["predicted"]
        wk["actual"] += e["actual"]
    daily_cmp = [
        {"date": k, "predicted": round(v["predicted"], 1), "actual": v["actual"]}
        for k, v in sorted(weekly.items())
    ]

    daily_cash = [
        {
            "date": r["date"],
            "revenue": r["revenue"],
            "cost": r["cost"],
            "lost_r": r["lost_r"],
        }
        for r in engine.daily_series
    ]

    stock_level = [r["demand_units"] for r in engine.daily_series]
    return {
        "summary": summary,
        "clean_summary": clean_overall,
        "rate_wape_pct": summary.get("rate_wape_pct"),
        "verdict": verdict(summary, engine.snapshot()["cash"]),
        "per_category": per_category,
        "daily_compare": daily_cmp,
        "daily_cash": daily_cash,
        "totals": {
            "days": engine.total_days,
            "revenue": round(engine.revenue, 2),
            "cost": round(engine.purchase_cost, 2),
            "profit": round(engine.revenue - engine.purchase_cost, 2),
            "lost_r": round(engine.lost_revenue, 2),
            "demand_units": sum(stock_level),
            "avg_daily_demand": round(statistics.mean(stock_level), 1) if stock_level else 0,
        },
        "events": engine.event_log,
    }
