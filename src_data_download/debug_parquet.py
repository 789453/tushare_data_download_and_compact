import pandas as pd
import pyarrow.parquet as pq
from pathlib import Path

def check_file(name, path):
    print(f"--- Checking {name} at {path} ---")
    p = Path(path)
    if not p.exists():
        print(f"File DOES NOT EXIST: {path}")
        return
    print(f"File exists: {path}")
    try:
        pf = pq.ParquetFile(p)
        print(f"Columns: {pf.schema.names}")
        print(f"Row count: {pf.metadata.num_rows}")
        if pf.metadata.num_rows > 0:
            # Try to read first few rows
            df = pd.read_parquet(p).head(5)
            print("First 5 rows:")
            print(df)
            
            # Check trade_date
            if "trade_date" in df.columns:
                print(f"trade_date max: {df['trade_date'].astype(str).max()}")
            else:
                print("Column 'trade_date' NOT FOUND")
    except Exception as e:
        print(f"Error reading file: {e}")

raw_dir = r"d:\Trading\data_ever_26_3_14\data\Raw_data"
check_file("daily", f"{raw_dir}/daily.parquet")
check_file("daily_basic", f"{raw_dir}/daily_basic.parquet")
check_file("moneyflow", f"{raw_dir}/moneyflow.parquet")
check_file("cyq_perf", f"{raw_dir}/cyq_perf.parquet")
check_file("stk_mins_60min", f"{raw_dir}/stk_mins_60min.parquet")
