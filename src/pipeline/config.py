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

# Sensitivity analysis only — the official baseline is MA_WINDOW, fixed before
# looking at any test error (choosing k on the test set would be calibrating on it).
SENSITIVITY_WINDOWS = (1, 8, 13)

# Step 3 selection, declared before any forecast error was computed
# (notebooks/02_agregacao_e_selecao.ipynb). Criteria: full history since
# Jan/2013 and no zero week; a large store (44, Quito, type A) and a small one
# (54, El Carmen, type C); perishable and non-perishable families with a direct
# app category. Clean, high-volume series flatter the error: declared limitation.
SELECTED_SERIES: list[tuple[int, str]] = [
    (44, "GROCERY I"),
    (44, "BEVERAGES"),
    (44, "DAIRY"),
    (44, "BREAD/BAKERY"),
    (54, "GROCERY I"),
    (54, "BEVERAGES"),
    (54, "DAIRY"),
    (54, "BREAD/BAKERY"),
]
