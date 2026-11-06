import pandas as pd
import pytest

from pipeline.config import RAW_DIR


@pytest.fixture(scope="session")
def real_daily():
    if not (RAW_DIR / "train.csv").exists():
        pytest.skip("data/raw/favorita/train.csv ausente (dado bruto não versionado)")
    from pipeline.data import load_train

    return load_train()


def make_daily(start: str, end: str, series=((1, "A"),), value=1.0, drop=()) -> pd.DataFrame:
    """Synthetic long panel: one row per day x series, optionally dropping dates."""
    dates = [d for d in pd.date_range(start, end) if d.strftime("%Y-%m-%d") not in drop]
    rows = [
        {"date": d, "store_nbr": s, "family": f, "sales": value, "onpromotion": 0}
        for d in dates
        for s, f in series
    ]
    df = pd.DataFrame(rows)
    df["family"] = df["family"].astype("category")
    return df
