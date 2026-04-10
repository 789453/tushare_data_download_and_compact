import pandas as pd
import tushare as ts
import os
from pathlib import Path
from ts_download_utils import load_tushare_pro, retry_call, write_parquet_atomic
import numpy as np
import time

def update_stock_basics():
    """
    Downloads stock basic information (industry, market, list_date, delist_date)
    and updates the index_daily_basic_circ_mv.parquet file.
    """
    parquet_path = Path(r'd:\Trading\data_ever_26_3_14\data\Raw_data\index_daily_basic_circ_mv.parquet')
    if not parquet_path.exists():
        print(f"File not found: {parquet_path}")
        return
        
    df = pd.read_parquet(parquet_path)
    print(f"Loaded {len(df)} rows from {parquet_path}")
    
    # Check current columns
    print(f"Current columns: {df.columns.tolist()}")
    
    pro = load_tushare_pro()
    
    # 1. Fetch info from stock_basic (name, industry, market, list_date, delist_date)
    print("Fetching stock_basic for info (name, industry, market, list_date, delist_date)...")
    # stock_basic provides current industry, market, etc. which is sufficient for many use cases
    sb = retry_call(lambda: pro.stock_basic(fields='ts_code,symbol,name,industry,market,list_date,delist_date'))
    if sb is None or sb.empty:
        print("Failed to fetch stock_basic data from Tushare.")
        return
        
    # Merge info
    # Remove existing columns if they already exist to avoid duplicates
    cols_to_add = ['name', 'industry', 'market', 'list_date', 'delist_date']
    for col in cols_to_add:
        if col in df.columns:
            df = df.drop(columns=[col])
            
    df = df.merge(sb[['ts_code', 'name', 'industry', 'market', 'list_date', 'delist_date']], on='ts_code', how='left')
    
    print(f"Final columns: {df.columns.tolist()}")
    
    # Write back
    write_parquet_atomic(parquet_path, df)
    print(f"Successfully updated {parquet_path}")
    
    # Write back
    write_parquet_atomic(parquet_path, df)
    print(f"Successfully updated {parquet_path}")

if __name__ == "__main__":
    update_stock_basics()
