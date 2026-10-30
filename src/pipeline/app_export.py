"""Compact Favorita artifacts for the app: `python -m pipeline.app_export`.

The raw Favorita CSV (121 MB) stays out of git. The app only needs two small
derived tables, written to datasets/favorita/ (mounted read-only in the
backend container at /datasets/favorita):

  semanal.csv.gz     weekly sales of every store x family series, from the
                     week the series starts selling (leading zeros are "not yet
                     registered", not demand), with the app category, the store
                     size bucket and the number of national holidays in the week.
                     Trains and validates the production weekly model.
  perfil_diario.csv  detrended seasonal index per app category x store size x
                     month x weekday. Shapes the cold-start prior of products that
                     have no history yet.

Both are regenerated from data/raw/ by this command; never edited by hand.
"""

import numpy as np
import pandas as pd

from pipeline.config import ROOT_DIR
from pipeline.data import load_holidays, load_train
from pipeline.weekly import SERIES_KEYS, to_weekly

EXPORT_DIR = ROOT_DIR / "datasets" / "favorita"
ALL_CATEGORIES = "__all__"

# Favorita family -> app category (backend/app/services/seed_data.py).
FAMILY_TO_CATEGORY = {
    "AUTOMOTIVE": "Diversos",
    "BABY CARE": "Pet e Bebê",
    "BEAUTY": "Higiene e Beleza",
    "BEVERAGES": "Bebidas",
    "BOOKS": "Festa e Papelaria",
    "BREAD/BAKERY": "Padaria",
    "CELEBRATION": "Festa e Papelaria",
    "CLEANING": "Limpeza",
    "DAIRY": "Laticínios e Ovos",
    "DELI": "Congelados e Frios",
    "EGGS": "Laticínios e Ovos",
    "FROZEN FOODS": "Congelados e Frios",
    "GROCERY I": "Mercearia",
    "GROCERY II": "Mercearia",
    "HARDWARE": "Lar e Cozinha",
    "HOME AND KITCHEN I": "Lar e Cozinha",
    "HOME AND KITCHEN II": "Lar e Cozinha",
    "HOME APPLIANCES": "Lar e Cozinha",
    "HOME CARE": "Limpeza",
    "LADIESWEAR": "Diversos",
    "LAWN AND GARDEN": "Diversos",
    "LINGERIE": "Diversos",
    "LIQUOR,WINE,BEER": "Bebidas",
    "MAGAZINES": "Festa e Papelaria",
    "MEATS": "Carnes e Aves",
    "PERSONAL CARE": "Higiene e Beleza",
    "PET SUPPLIES": "Pet e Bebê",
    "PLAYERS AND ELECTRONICS": "Diversos",
    "POULTRY": "Carnes e Aves",
    "PREPARED FOODS": "Congelados e Frios",
    "PRODUCE": "Hortifrúti",
    "SCHOOL AND OFFICE SUPPLIES": "Festa e Papelaria",
    "SEAFOOD": "Peixes e Frutos do Mar",
}

# One-off shocks that must not shape a "typical" month x weekday pattern.
EXCLUDED_DAYS = pd.to_datetime(["2013-01-01", "2014-01-01", "2015-01-01", "2016-01-01", "2017-01-01"])
EARTHQUAKE = (pd.Timestamp("2016-04-16"), pd.Timestamp("2016-05-15"))


def national_holidays(holidays: pd.DataFrame) -> pd.Series:
    """Dates of national days off (transferred holidays count on the day they were moved to)."""
    nat = holidays[
        (holidays["locale"] == "National")
        & (~holidays["transferred"])
        & (holidays["type"].isin(["Holiday", "Additional", "Bridge", "Transfer"]))
    ]
    return nat["date"].drop_duplicates()


def store_size_buckets(daily: pd.DataFrame) -> pd.Series:
    """Store volume quartile (0 = smallest), the dataset analogue of the app's customers/day bucket."""
    volume = daily.groupby("store_nbr")["sales"].sum()
    return pd.Series(pd.qcut(volume.rank(method="first"), 4, labels=False), index=volume.index).astype(int)


def weekly_export(daily: pd.DataFrame, holidays: pd.DataFrame, sizes: pd.Series) -> pd.DataFrame:
    weekly = to_weekly(daily)
    weekly["family"] = weekly["family"].astype(str)
    born = weekly[weekly["sales"] > 0].groupby(SERIES_KEYS)["week_start"].min().rename("born")
    weekly = weekly.merge(born, on=SERIES_KEYS)
    weekly = weekly[weekly["week_start"] >= weekly["born"]].drop(columns=["born", "onpromotion", "n_days"])

    hol = national_holidays(holidays)
    per_week = (hol - pd.to_timedelta(hol.dt.weekday, unit="D")).value_counts()
    weekly["holiday_days"] = weekly["week_start"].map(per_week).fillna(0).astype(int)
    weekly["category"] = weekly["family"].map(FAMILY_TO_CATEGORY)
    weekly["size_bucket"] = weekly["store_nbr"].map(sizes).astype(int)
    weekly["sales"] = weekly["sales"].round(3)
    cols = ["store_nbr", "family", "category", "size_bucket", "week_start", "sales", "holiday_days"]
    return weekly[cols].sort_values(["store_nbr", "family", "week_start"]).reset_index(drop=True)


def daily_profile(daily: pd.DataFrame, sizes: pd.Series) -> pd.DataFrame:
    """Seasonal index per category x size x month x weekday, with the trend removed.

    Each series-day is divided by the series' centered one-year moving average,
    so growth over 2013-2017 does not leak into the month effect. Only days after
    the series starts selling count; 1 January (stores closed) and the 2016
    earthquake month are left out.
    """
    df = daily[["date", "store_nbr", "family", "sales"]].copy()
    df["family"] = df["family"].astype(str)
    df = df.sort_values(["store_nbr", "family", "date"])
    first = df[df["sales"] > 0].groupby(SERIES_KEYS)["date"].min().rename("born")
    df = df.merge(first, on=SERIES_KEYS)
    df = df[df["date"] >= df["born"]]
    df["trend"] = df.groupby(SERIES_KEYS, sort=False)["sales"].transform(
        lambda s: s.rolling(365, center=True, min_periods=180).mean()
    )
    df = df[(df["trend"] > 0) & ~df["date"].isin(EXCLUDED_DAYS)]
    df = df[~df["date"].between(*EARTHQUAKE)]
    df["index"] = (df["sales"] / df["trend"]).clip(upper=10)
    df["category"] = df["family"].map(FAMILY_TO_CATEGORY)
    df["size_bucket"] = df["store_nbr"].map(sizes).astype(int)
    df["month"] = df["date"].dt.month
    df["weekday"] = df["date"].dt.weekday

    keys = ["size_bucket", "month", "weekday"]
    by_cat = df.groupby(["category"] + keys)["index"].agg(["mean", "size"]).reset_index()
    overall = df.groupby(keys)["index"].agg(["mean", "size"]).reset_index().assign(category=ALL_CATEGORIES)
    out = pd.concat([by_cat, overall], ignore_index=True).rename(columns={"mean": "index", "size": "n_obs"})
    out["index"] = out["index"].round(4)
    return out[["category", "size_bucket", "month", "weekday", "index", "n_obs"]].sort_values(
        ["category", "size_bucket", "month", "weekday"]
    ).reset_index(drop=True)


def main() -> None:
    daily = load_train()
    holidays = load_holidays()
    sizes = store_size_buckets(daily)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    weekly = weekly_export(daily, holidays, sizes)
    weekly.to_csv(EXPORT_DIR / "semanal.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    profile = daily_profile(daily, sizes)
    profile.to_csv(EXPORT_DIR / "perfil_diario.csv", index=False)

    n_series = weekly.groupby(SERIES_KEYS).ngroups
    print(f"semanal.csv.gz: {len(weekly):,} linhas, {n_series} séries, {weekly['week_start'].nunique()} semanas")
    print(f"perfil_diario.csv: {len(profile):,} linhas, {profile['category'].nunique()} categorias (inclui {ALL_CATEGORIES})")
    for f in ("semanal.csv.gz", "perfil_diario.csv"):
        print(f"  {f}: {(EXPORT_DIR / f).stat().st_size / 1e6:.2f} MB")
    print(np.round(profile[profile.category == ALL_CATEGORIES].groupby("weekday")["index"].mean(), 3).to_dict())


if __name__ == "__main__":
    main()
