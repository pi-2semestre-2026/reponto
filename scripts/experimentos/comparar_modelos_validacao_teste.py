"""Experiment: global weekly LightGBM on Favorita vs baselines (incl. app's EMA)."""
import sys, time
import numpy as np, pandas as pd, lightgbm as lgb
from pipeline.data import load_train, load_holidays, load_stores
from pipeline.weekly import to_weekly

REFIT = int(sys.argv[1]) if len(sys.argv) > 1 else 13
FAMILY_TO_CATEGORY = {
    "AUTOMOTIVE": "Diversos", "BABY CARE": "Pet e Bebê", "BEAUTY": "Higiene e Beleza", "BEVERAGES": "Bebidas",
    "BOOKS": "Festa e Papelaria", "BREAD/BAKERY": "Padaria", "CELEBRATION": "Festa e Papelaria", "CLEANING": "Limpeza",
    "DAIRY": "Laticínios e Ovos", "DELI": "Congelados e Frios", "EGGS": "Laticínios e Ovos", "FROZEN FOODS": "Congelados e Frios",
    "GROCERY I": "Mercearia", "GROCERY II": "Mercearia", "HARDWARE": "Lar e Cozinha", "HOME AND KITCHEN I": "Lar e Cozinha",
    "HOME AND KITCHEN II": "Lar e Cozinha", "HOME APPLIANCES": "Lar e Cozinha", "HOME CARE": "Limpeza", "LADIESWEAR": "Diversos",
    "LAWN AND GARDEN": "Diversos", "LINGERIE": "Diversos", "LIQUOR,WINE,BEER": "Bebidas", "MAGAZINES": "Festa e Papelaria",
    "MEATS": "Carnes e Aves", "PERSONAL CARE": "Higiene e Beleza", "PET SUPPLIES": "Pet e Bebê",
    "PLAYERS AND ELECTRONICS": "Diversos", "POULTRY": "Carnes e Aves", "PREPARED FOODS": "Congelados e Frios",
    "PRODUCE": "Hortifrúti", "SCHOOL AND OFFICE SUPPLIES": "Festa e Papelaria", "SEAFOOD": "Peixes e Frutos do Mar",
}
CATS = sorted(set(FAMILY_TO_CATEGORY.values()))

t0 = time.time()
daily = load_train()
w = to_weekly(daily)
w["family"] = w["family"].astype(str)
# trim leading zeros: series "born" at first positive week
first = w[w.sales > 0].groupby(["store_nbr", "family"]).week_start.min().rename("born")
w = w.merge(first, on=["store_nbr", "family"])
w = w[w.week_start >= w.born].drop(columns="born")
vol = w.groupby("store_nbr").sales.sum()
w["size_bucket"] = w.store_nbr.map(pd.Series(pd.qcut(vol.rank(method="first"), 4, labels=False), index=vol.index)).astype(int)
w["category"] = pd.Categorical(w.family.map(FAMILY_TO_CATEGORY), categories=CATS).codes
h = load_holidays()
nat = h[(h.locale == "National") & (~h.transferred) & (h.type.isin(["Holiday", "Additional", "Bridge", "Transfer"]))]
hw = (nat.date - pd.to_timedelta(nat.date.dt.weekday, unit="D")).value_counts()
w["holiday_days"] = w.week_start.map(hw).fillna(0).astype(int)
w = w.sort_values(["store_nbr", "family", "week_start"]).reset_index(drop=True)
print(f"rows {len(w):,} series {w.groupby(['store_nbr','family']).ngroups} load {time.time()-t0:.0f}s")

key = [w.store_nbr, w.family]
g = w.groupby(["store_nbr", "family"], sort=False).sales
for k in (1, 2, 3, 4, 52):
    w[f"lag{k}"] = g.shift(k)
sh = g.shift(1)
sg = sh.groupby(key, sort=False)
w["level"] = sg.transform(lambda s: s.rolling(8).mean())
w["ma4"] = sg.transform(lambda s: s.rolling(4).mean())
w["std8"] = sg.transform(lambda s: s.rolling(8).std())
w["ma4_prev"] = g.shift(5).groupby(key, sort=False).transform(lambda s: s.rolling(4).mean())
# app's rule: EMA with half-life 30 days over a 90-day window -> weekly weights 2^(-7a/30), 13 weeks
wts = np.array([2 ** (-7 * a / 30) for a in range(13)])
def ema(s):
    v = s.to_numpy(); out = np.full(len(v), np.nan)
    for i in range(len(v)):
        past = v[max(0, i - 13):i][::-1]
        if len(past) >= 4 and not np.isnan(past).any():
            ww = wts[:len(past)]; out[i] = (past * ww).sum() / ww.sum()
    return pd.Series(out, index=s.index)
w["ema"] = g.transform(ema)
w = w[w.level > 0].copy()
for k in (1, 2, 3, 4, 52):
    w[f"r_lag{k}"] = w[f"lag{k}"] / w.level
w["r_ma4"] = w.ma4 / w.level
w["cv8"] = w.std8 / w.level
w["trend"] = w.ma4 / w.ma4_prev
w["weekofyear"] = w.week_start.dt.isocalendar().week.astype(int)
w["month"] = w.week_start.dt.month
w["ratio"] = w.sales / w.level
w["log_level"] = np.log1p(w.level)
w["zero8"] = sh.groupby(key, sort=False).transform(lambda s: (s == 0).astype(float).rolling(8).mean()).reindex(w.index)
print(f"features ready {time.time()-t0:.0f}s, rows {len(w):,}")

BASE = ["r_lag1", "r_lag2", "r_lag3", "r_lag4", "r_lag52", "r_ma4", "cv8", "trend", "weekofyear", "month", "size_bucket"]

EXTRA = ["log_level", "zero8"]
VARIANTS = {
    "base_l2": (BASE, "regression"),
    "tw13": (BASE + EXTRA, "tweedie"),
    "tw13_cat": (BASE + EXTRA + ["category"], "tweedie"),
    "tw13_cat_hol": (BASE + EXTRA + ["category", "holiday_days"], "tweedie"),
}
def params(obj):
    extra = {"tweedie_variance_power": 1.3} if obj == "tweedie" else {}
    return {**extra, "objective": obj, "learning_rate": 0.05, "num_leaves": 63, "min_data_in_leaf": 100, "feature_fraction": 0.9,
            "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0, "seed": 42, "verbose": -1}
weeks = sorted(w.week_start.unique())
periods = {"validacao": weeks[-104:-52], "teste": weeks[-52:]}
def run(period, feats, obj):
    origins = period[::REFIT]; test = w[w.week_start.isin(period)].copy(); preds = pd.Series(np.nan, index=test.index)
    for i, o in enumerate(origins):
        end = origins[i + 1] if i + 1 < len(origins) else None
        tr = w[w.week_start < o]; m = (test.week_start >= o) & ((test.week_start < end) if end is not None else True)
        cat = ["category"] if "category" in feats else "auto"
        if obj == "tweedie":
            mdl = lgb.train(params(obj), lgb.Dataset(tr[feats], label=tr.sales, init_score=np.log(tr.level), categorical_feature=cat), 400)
            preds[m] = np.exp(mdl.predict(test.loc[m, feats], raw_score=True)) * test.loc[m, "level"]
        else:
            mdl = lgb.train(params(obj), lgb.Dataset(tr[feats], label=tr.ratio, weight=tr.level, categorical_feature=cat), 400)
            preds[m] = np.clip(mdl.predict(test.loc[m, feats]), 0, None) * test.loc[m, "level"]
    return preds
def wape(d, c): return 100 * (d[c] - d.sales).abs().sum() / d.sales.sum()
TIERS = [0, 20, 200, 2000, np.inf]; LABELS = ["<20", "20-200", "200-2k", ">2k"]
res = {}
for pname, period in periods.items():
    df = w[w.week_start.isin(period)].copy()
    for name, (feats, obj) in VARIANTS.items():
        df[f"p_{name}"] = run(period, feats, obj)
    df["p_ma4"] = df.ma4; df["p_ema"] = df.ema
    cols = [c for c in df.columns if c.startswith("p_")]
    df = df.dropna(subset=cols); df["tier"] = pd.cut(df.level, TIERS, labels=LABELS)
    tab = pd.DataFrame({c[2:]: {"WAPE": wape(df, c), **{t: wape(df[df.tier == t], c) for t in LABELS}} for c in cols}).T
    print(f"\n=== {pname} ({pd.Timestamp(period[0]).date()} .. {pd.Timestamp(period[-1]).date()}), rows {len(df):,}")
    print(tab.round(2).sort_values("WAPE").to_string())
    res[pname] = df
# conformal: calibrate q on validation, measure coverage on test (chosen model)
best = "p_tw13_cat_hol"
val, tst = res["validacao"], res["teste"]
print("\n=== intervalo superior 95% (calibrado na validação, medido no teste)")
for t in LABELS:
    u = (val.loc[val.tier == t, "sales"] / val.loc[val.tier == t, best]).replace([np.inf], np.nan).dropna()
    q = float(np.quantile(u, 0.95))
    tt = tst[tst.tier == t]
    cov = float((tt.sales <= tt[best] * q).mean() * 100)
    print(f"{t:>7}: q95={q:.3f}  cobertura no teste={cov:.1f}%  (n={len(tt)})")
u = (val.sales / val[best]).replace([np.inf], np.nan).dropna(); q = np.quantile(u, 0.95)
print(f"global q95={q:.3f} cobertura={float((tst.sales <= tst[best]*q).mean()*100):.1f}%")
