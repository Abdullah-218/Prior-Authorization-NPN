"""Central configuration — shared by train.py, predict.py, business_metrics.py.

Extends the reference config.py (FEATURES/TARGET/GROUP_COLUMN/RANDOM_STATE/
DECISION_THRESHOLD kept exactly as given) with resolved project paths, so
nothing downstream hardcodes a path string.
"""
from pathlib import Path

# ---- reference constants, unchanged ----
FEATURES = ["policy_score", "documentation_score", "clinical_evidence_score", "diagnosis_supported"]
TARGET = "label"
GROUP_COLUMN = "patient_id"
RANDOM_STATE = 42
DECISION_THRESHOLD = None  # loaded from model artifact during prediction

# ---- paths ----
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "processed"
ML_TRAINING_SET_PATH = DATA_DIR / "ml_training_set.csv"
FULL_REQUESTS_PATH = DATA_DIR / "full_requests.csv"

MODEL_DIR = ROOT / "models"
MODEL_PATH = MODEL_DIR / "proauth_best_model.pkl"

REPORTS_DIR = ROOT / "reports"
VIZ_DIR = ROOT / "visualizations"
POWERBI_DIR = ROOT / "powerbi"

for d in (MODEL_DIR, REPORTS_DIR, VIZ_DIR, POWERBI_DIR):
    d.mkdir(parents=True, exist_ok=True)

# splits present in the supplied dataset — respected as-is, never re-cut
SPLIT_TRAIN = "train"
SPLIT_VAL = "val"
SPLIT_TEST = "test"
SPLIT_HOLDOUT_CATEGORY = "holdout_category"

TARGET_ACCURACY = 80.0        # required minimum, on BOTH test and holdout_category
OVERFIT_GAP_MAX = 4.0         # percentage points; train_acc - val_acc above this = reject
UNDERFIT_TRAIN_ACC_MIN = 68.0 # percentage; train_acc below this = reject
