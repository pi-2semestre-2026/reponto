"""Paths and fixed decisions of the ML pipeline (see docs/PLANO_ML.md)."""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT_DIR / "data" / "raw" / "favorita"
PROCESSED_DIR = ROOT_DIR / "data" / "processed"
REPORTS_DIR = ROOT_DIR / "reports"

# Evaluation protocol — shared with Phase 2, do not change without re-running both.
TEST_WEEKS = 52
HORIZON = 1
MA_WINDOW = 4

# (store_nbr, family) pairs; filled in step 3 after the series selection.
SELECTED_SERIES: list[tuple[int, str]] = []
