import os
from pathlib import Path

# Base Paths
PROJECT_ROOT = Path(r"d:\Trading\data_ever_26_3_14")
DATA_ROOT = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_ROOT / "Raw_data"
FEATURE_DATA_DIR = DATA_ROOT / "Feature_data"
DOMAIN_DATA_DIR = FEATURE_DATA_DIR / "domain"
FACTOR_READY_DIR = FEATURE_DATA_DIR / "factor_ready"
MODEL_DATA_DIR = DATA_ROOT / "Model_data"

# Raw File Paths
RAW_DAILY = RAW_DATA_DIR / "daily.parquet"
RAW_DAILY_BASIC = RAW_DATA_DIR / "daily_basic.parquet"
RAW_MONEYFLOW = RAW_DATA_DIR / "moneyflow.parquet"
RAW_CYQ_PERF = RAW_DATA_DIR / "cyq_perf.parquet"
RAW_STK_MINS = RAW_DATA_DIR / "stk_60_mins.parquet"

# Output File Paths
FEATURE_REGISTRY_PATH = FACTOR_READY_DIR / "feature_registry.csv"

# Constants
EPSILON = 1e-8

# Start Dates
START_DATE_B = "20100101"  # Moneyflow
START_DATE_C = "20180101"  # Chip/CYQ

# Data Types
# Ensure consistency in ID columns
ID_COLUMNS = ["ts_code", "trade_date"]
