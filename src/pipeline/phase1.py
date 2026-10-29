"""Phase 1, end to end: `python -m pipeline.phase1`.

raw CSV -> weekly panel -> SELECTED_SERIES -> data/processed/favorita_weekly.parquet
-> moving-average baseline (official k plus sensitivity) -> reports/fase1_baseline.csv
(+ data/processed/fase1_residuals.parquet, the Phase 4 input).
Running it twice gives identical numbers.
"""

import pandas as pd

from pipeline.baseline import moving_average_forecast
from pipeline.config import HORIZON, MA_WINDOW, PROCESSED_DIR, REPORTS_DIR, SELECTED_SERIES, SENSITIVITY_WINDOWS, TEST_WEEKS
from pipeline.data import load_train
from pipeline.evaluation import evaluate
from pipeline.weekly import select_series, to_weekly


def run() -> pd.DataFrame:
    weekly = select_series(to_weekly(load_train()), SELECTED_SERIES)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    weekly.to_parquet(PROCESSED_DIR / "favorita_weekly.parquet", index=False)

    tables = []
    for k in (MA_WINDOW, *SENSITIVITY_WINDOWS):
        scored = weekly.assign(forecast=moving_average_forecast(weekly, window=k, horizon=HORIZON))
        per_series, residuals = evaluate(scored, test_weeks=TEST_WEEKS)
        tables.append(per_series.assign(k=k, official=(k == MA_WINDOW)))
        if k == MA_WINDOW:
            residuals.to_parquet(PROCESSED_DIR / "fase1_residuals.parquet", index=False)

    report = pd.concat(tables, ignore_index=True)
    report.insert(0, "series", report["store_nbr"].astype(str) + " · " + report["family"].astype(str))
    report = report[["series", "store_nbr", "family", "k", "official", "mae", "mape", "mape_ignored", "wape", "bias", "points"]]
    report = report.round({"mae": 2, "mape": 2, "wape": 2, "bias": 2})
    report.to_csv(REPORTS_DIR / "fase1_baseline.csv", index=False)
    return report


def main() -> None:
    report = run()
    official = report[report["official"]]
    print(f"{len(official)} séries, baseline média móvel k={MA_WINDOW}, {TEST_WEEKS} semanas de teste")
    print(official[["series", "mae", "mape", "wape", "bias", "points"]].to_string(index=False))
    print("\nSensibilidade (MAPE médio por k):")
    print(report.groupby("k")["mape"].mean().round(2).to_string())
    print(f"\nGravado: {PROCESSED_DIR / 'favorita_weekly.parquet'} e {REPORTS_DIR / 'fase1_baseline.csv'}")


if __name__ == "__main__":
    main()
