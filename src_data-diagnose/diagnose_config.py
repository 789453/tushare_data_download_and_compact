
import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(r"d:\Trading\data_ever_26_3_14")
DATA_DIR = BASE_DIR / "data"
SRC_DIR = BASE_DIR / "src_data-diagnose"

# Input Data Paths
RAW_DATA_DIR = DATA_DIR / "Raw_data"
FEATURE_READY_DIR = DATA_DIR / "Feature_data" / "factor_ready"
DOMAIN_DATA_DIR = DATA_DIR / "Feature_data" / "domain"

# Output Paths
OUTPUT_DIR = DATA_DIR / "data_diagnose"
IMG_DIR = OUTPUT_DIR / "images"
REPORT_DIR = OUTPUT_DIR / "reports"

# Create output directories if they don't exist
IMG_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# Matplotlib Font Configuration for Chinese Support
FONT_PATH = r"C:\Windows\Fonts\msyh.ttc"  # Microsoft YaHei
FONT_NAME = "Microsoft YaHei"

# Analysis Parameters
QUANTILES = [0.01, 0.05, 0.25, 0.50, 0.75, 0.95, 0.99]
