"""Loaders for the raw Favorita files (read-only: data/raw/ is never edited)."""

import pandas as pd

from pipeline.config import RAW_DIR


def load_train() -> pd.DataFrame:
    """Daily panel in long format: one row per date x store x family.

    `sales` is the total units of the family sold in the store that day
    (fractional for items sold by weight); `onpromotion` is the number of
    items of the family on promotion.
    """
    df = pd.read_csv(
        RAW_DIR / "train.csv",
        parse_dates=["date"],
        dtype={"id": "int32", "store_nbr": "int16", "onpromotion": "int32"},
    )
    df["family"] = df["family"].astype("category")
    return df


def load_stores() -> pd.DataFrame:
    """Store attributes: city, state, type and cluster."""
    return pd.read_csv(RAW_DIR / "stores.csv")


def load_holidays() -> pd.DataFrame:
    """Holidays and events (used from Phase 2; handy for the exploration)."""
    return pd.read_csv(RAW_DIR / "holidays_events.csv", parse_dates=["date"])
