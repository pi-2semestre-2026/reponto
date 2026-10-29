import pandas as pd

from pipeline.weekly import complete_weeks, select_series, to_weekly
from tests.pipeline.conftest import make_daily


def test_partial_edge_weeks_are_dropped():
    # 2013-01-01 is a Tuesday and 2013-01-22 a Tuesday: only the 2 full weeks in between remain.
    daily = make_daily("2013-01-01", "2013-01-22")
    weekly = to_weekly(daily)
    assert list(weekly["week_start"]) == [pd.Timestamp("2013-01-07"), pd.Timestamp("2013-01-14")]
    assert (weekly["n_days"] == 7).all()
    assert (weekly["sales"] == 7.0).all()


def test_week_is_labelled_by_monday_and_sums_days():
    daily = make_daily("2013-01-07", "2013-01-13")
    daily["sales"] = range(1, 8)  # Mon=1 ... Sun=7
    weekly = to_weekly(daily)
    assert len(weekly) == 1
    assert weekly.loc[0, "week_start"] == pd.Timestamp("2013-01-07")
    assert weekly.loc[0, "sales"] == 28


def test_missing_day_counts_in_n_days_not_as_zero():
    daily = make_daily("2013-12-23", "2013-12-29", drop=("2013-12-25",))
    weekly = to_weekly(daily)
    assert weekly.loc[0, "n_days"] == 6
    assert weekly.loc[0, "sales"] == 6.0


def test_series_never_mix():
    daily = make_daily("2013-01-07", "2013-01-20", series=((1, "A"), (2, "A"), (1, "B")))
    weekly = to_weekly(daily)
    assert len(weekly) == 3 * 2
    assert weekly.groupby(["store_nbr", "family"], observed=True).size().eq(2).all()


def test_select_series_keeps_only_requested_pairs():
    daily = make_daily("2013-01-07", "2013-01-13", series=((1, "A"), (2, "B")))
    picked = select_series(to_weekly(daily), [(2, "B")])
    assert picked[["store_nbr", "family"]].drop_duplicates().values.tolist() == [[2, "B"]]


# ---- Real data: the "Pronto quando" of step 2 ----

def test_real_every_series_has_240_weeks_without_nan(real_daily):
    weekly = to_weekly(real_daily)
    sizes = weekly.groupby(["store_nbr", "family"], observed=True).size()
    assert len(sizes) == 1782 and (sizes == 240).all()
    assert not weekly[["sales", "onpromotion", "n_days"]].isna().any().any()
    first, last = complete_weeks(real_daily["date"])
    assert (first, last) == (pd.Timestamp("2013-01-07"), pd.Timestamp("2017-08-07"))


def test_real_weekly_sum_equals_daily_sum(real_daily):
    weekly = to_weekly(real_daily)
    inside = real_daily[(real_daily["date"] >= "2013-01-07") & (real_daily["date"] <= "2017-08-13")]
    assert abs(weekly["sales"].sum() - inside["sales"].sum()) < 1e-3 * inside["sales"].sum() / 1e6


def test_real_n_days_is_6_only_in_the_four_christmas_weeks(real_daily):
    weekly = to_weekly(real_daily)
    short = sorted(weekly.loc[weekly["n_days"] != 7, "week_start"].unique())
    assert [pd.Timestamp(w).strftime("%Y-%m-%d") for w in short] == ["2013-12-23", "2014-12-22", "2015-12-21", "2016-12-19"]
    assert (weekly.loc[weekly["n_days"] != 7, "n_days"] == 6).all()
