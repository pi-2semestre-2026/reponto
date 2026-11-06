"""Weekly aggregation: Monday to Sunday, labelled by the Monday.

Sales are a flow variable, so the week is the SUM of its days. Only complete
calendar weeks are kept: the raw file starts and ends on a Tuesday, and a
partial first/last week would look like a sudden drop in demand.
"""

import pandas as pd

SERIES_KEYS = ["store_nbr", "family"]


def week_start(dates: pd.Series) -> pd.Series:
    """Monday of the week of each date."""
    return dates - pd.to_timedelta(dates.dt.weekday, unit="D")


def complete_weeks(dates: pd.Series) -> tuple[pd.Timestamp, pd.Timestamp]:
    """First and last Monday whose full week (Mon-Sun) lies inside the data range."""
    first_day, last_day = dates.min(), dates.max()
    first = first_day + pd.Timedelta(days=(7 - first_day.weekday()) % 7)
    last = last_day - pd.Timedelta(days=last_day.weekday())
    if last + pd.Timedelta(days=6) > last_day:
        last -= pd.Timedelta(days=7)
    return first, last


def to_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    """One row per week x store x family.

    Columns: store_nbr, family, week_start, sales (sum), onpromotion (sum),
    n_days (days with a record; 6 in Christmas weeks, when 25/12 has no row).
    Series are grouped BEFORE aggregating in time, so stores and families
    never mix inside a week.
    """
    first, last = complete_weeks(daily["date"])
    df = daily.assign(week_start=week_start(daily["date"]))
    df = df[(df["week_start"] >= first) & (df["week_start"] <= last)]
    weekly = (
        df.groupby(SERIES_KEYS + ["week_start"], observed=True)
        .agg(sales=("sales", "sum"), onpromotion=("onpromotion", "sum"), n_days=("date", "nunique"))
        .reset_index()
        .sort_values(SERIES_KEYS + ["week_start"])
        .reset_index(drop=True)
    )
    weekly["n_days"] = weekly["n_days"].astype("int8")
    return weekly


def select_series(weekly: pd.DataFrame, series: list[tuple[int, str]]) -> pd.DataFrame:
    """Rows of the given (store_nbr, family) pairs, in the same order as the list."""
    keys = pd.DataFrame(series, columns=SERIES_KEYS)
    keys["family"] = keys["family"].astype(weekly["family"].dtype)
    out = weekly.merge(keys, on=SERIES_KEYS, how="inner")
    return out.sort_values(SERIES_KEYS + ["week_start"]).reset_index(drop=True)
