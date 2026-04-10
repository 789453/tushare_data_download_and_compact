from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq

def get_parquet_max_date_debug(path: Path, date_col: str = "trade_date") -> str | None:
    print(f"Testing path: {path}")
    if not path.exists():
        print("Path does not exist")
        return None
    try:
        pf = pq.ParquetFile(path)
        print(f"Num rows: {pf.metadata.num_rows}")
        if pf.metadata.num_rows == 0:
            return None
        
        print("Reading column...")
        df = pd.read_parquet(path, columns=[date_col])
        print(f"DF shape: {df.shape}")
        if df.empty:
            print("DF is empty")
            return None
        
        print("Calculating max...")
        val = df[date_col].astype(str).max()
        print(f"Max value: {val}")
        if "-" in val:
            val = val.replace("-", "")
        return val
    except Exception as e:
        print(f"Exception: {e}")
        return None

raw_dir = Path(r"d:\Trading\data_ever_26_3_14\data\Raw_data")
res = get_parquet_max_date_debug(raw_dir / "daily.parquet")
print(f"Result: {res}")
