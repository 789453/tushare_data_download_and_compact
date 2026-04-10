import pandas as pd
import pyarrow.parquet as pq
from pathlib import Path
import time
import argparse

def deduplicate_file(path: Path, pk_cols: list[str]) -> bool:
    if not path.exists():
        print(f"Skipping {path.name}: File not found")
        return False
    
    print(f"\n>>> Deduplicating {path.name}...")
    t0 = time.time()
    
    try:
        # Get original row count
        orig_rows = pq.ParquetFile(path).metadata.num_rows
        
        # Read file with pandas
        # To save memory, only read primary keys first to identify duplicates?
        # But we need to save the whole table, so we'll read it all.
        # Given memory constraints, we'll read it chunk by chunk if it's too large, 
        # but pandas.read_parquet doesn't support chunking easily for deduplication.
        # Let's try reading the whole table first.
        df = pd.read_parquet(path)
        
        new_df = df.drop_duplicates(subset=pk_cols, keep='first')
        new_rows = len(new_df)
        diff = orig_rows - new_rows
        
        if diff > 0:
            print(f"  Success: Removed {diff} duplicate rows ({orig_rows} -> {new_rows})")
            # Write to a temporary file first
            tmp_path = path.with_suffix(".dedup_tmp")
            # Preserve compression
            new_df.to_parquet(tmp_path, index=False, compression="zstd")
            
            # Replace original with deduplicated version
            bak_path = path.with_suffix(".bak_dedup")
            path.rename(bak_path)
            tmp_path.rename(path)
            bak_path.unlink()
        else:
            print(f"  No duplicates found. Row count: {orig_rows}")
            
        print(f"  Time taken: {time.time() - t0:.2f}s")
        return True
        
    except Exception as e:
        print(f"  Error deduplicating {path.name}: {e}")
        return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default=r"d:\Trading\data_ever_26_3_14\data\Raw_data")
    args = parser.parse_args()
    
    raw_dir = Path(args.raw_dir)
    
    files_to_dedup = [
        ("daily.parquet", ["ts_code", "trade_date"]),
        ("daily_basic.parquet", ["ts_code", "trade_date"]),
        ("moneyflow.parquet", ["ts_code", "trade_date"]),
        ("cyq_perf.parquet", ["ts_code", "trade_date"]),
        ("stk_60_mins.parquet", ["ts_code", "trade_time"]),
    ]
    
    for filename, pks in files_to_dedup:
        deduplicate_file(raw_dir / filename, pks)

if __name__ == "__main__":
    main()
