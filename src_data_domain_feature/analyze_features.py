import polars as pl
import json
import os
import pandas as pd
from pathlib import Path

try:
    from .config import FACTOR_READY_DIR, FEATURE_REGISTRY_PATH, FEATURE_DATA_DIR, RAW_DATA_DIR, PROJECT_ROOT
except ImportError:
    from config import FACTOR_READY_DIR, FEATURE_REGISTRY_PATH, FEATURE_DATA_DIR, RAW_DATA_DIR, PROJECT_ROOT

def get_column_category(col_name: str) -> str:
    if col_name in ["ts_code", "trade_date"]:
        return "Index Key"
    return "Dynamic Continuous"

def analyze_features():
    print("Starting Selected Raw Data Analysis...")
    
    # 1. Load Registry for descriptions (Optional fallback)
    descriptions = {
        "ts_code": "Stock code identifier (e.g., Code.Exchange)",
        "trade_date": "Trading date in YYYYMMDD format",
        "trade_time": "Trading timestamp (for minute data)",
        "up_limit": "Daily price upper limit",
        "down_limit": "Daily price lower limit",
        "suspend_type": "Suspension type (S for Suspend, R for Resume)",
        "suspend_timing": "Intraday suspension timing"
    }
    
    if Path(FEATURE_REGISTRY_PATH).exists():
        try:
            registry_df = pd.read_csv(FEATURE_REGISTRY_PATH)
            descriptions.update(dict(zip(registry_df['feature_name'], registry_df['notes'])))
        except Exception:
            pass
    
    output_json = {}
    
    # 2. Define specific files to process: top-level parquets in RAW_DATA_DIR and FACTOR_READY_DIR
    raw_files = list(RAW_DATA_DIR.glob("*.parquet"))
    feature_files = list(FACTOR_READY_DIR.glob("*.parquet"))
    
    target_files = raw_files + feature_files
    
    for file_path in target_files:
        if not file_path.is_file():
            continue
            
        # Prefix based on directory to avoid collisions and clarify source
        if RAW_DATA_DIR in file_path.parents:
            file_name = f"raw_{file_path.stem}"
        else:
            file_name = f"feat_{file_path.stem}"
            
        print(f"Analyzing {file_name} ({file_path.name})...")
        
        # Load with polars
        try:
            df = pl.read_parquet(file_path)
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            continue
            
        file_stats = {}
        
        for col in df.columns:
            series = df[col]
            dtype = str(series.dtype)
            
            # Example value (first non-null if possible)
            example_val = None
            if series.null_count() < len(series):
                example_val = series.drop_nulls().head(1).to_list()[0]
            
            # Missing rate
            missing_rate = series.null_count() / len(series)
            
            # Value range
            if series.dtype.is_numeric():
                v_min = series.min()
                v_max = series.max()
                value_range = [float(v_min) if v_min is not None else None, 
                               float(v_max) if v_max is not None else None]
            elif series.dtype == pl.Datetime:
                v_min = series.min()
                v_max = series.max()
                value_range = [str(v_min) if v_min is not None else None, 
                               str(v_max) if v_max is not None else None]
            else:
                # For non-numeric (like strings), just get unique range or sample
                try:
                    unique_vals = series.unique().sort().head(2).to_list()
                    if len(unique_vals) > 0:
                        v_min = unique_vals[0]
                        v_max = series.unique().sort(descending=True).head(1).to_list()[0] if len(unique_vals) > 1 else unique_vals[0]
                        value_range = [str(v_min), str(v_max)]
                    else:
                        value_range = [None, None]
                except:
                    value_range = [None, None]
            
            file_stats[col] = {
                "category": get_column_category(col),
                "example_value": str(example_val) if example_val is not None else None,
                "dtype": dtype,
                "missing_rate": missing_rate,
                "value_range": value_range,
                "description": descriptions.get(col, f"Field {col} from {file_path.name}")
            }
            
        output_json[file_name] = file_stats
        
    # 3. Save JSON to Json_format_data
    output_dir = PROJECT_ROOT / "data" / "Json_format_data"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "raw_data_stats.json"
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_json, f, indent=4, ensure_ascii=False)
        
    print(f"Analysis complete. JSON saved to {output_path}")

if __name__ == "__main__":
    analyze_features()
