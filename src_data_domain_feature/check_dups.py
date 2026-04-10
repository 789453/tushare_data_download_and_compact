import pandas as pd
from config import RAW_DAILY, RAW_MONEYFLOW
from utils_io import load_parquet

def check_duplicates():
    print("Checking daily...")
    df_daily = load_parquet(RAW_DAILY, columns=['ts_code', 'trade_date'])
    dup_daily = df_daily.duplicated(subset=['ts_code', 'trade_date']).sum()
    print(f"Daily duplicates: {dup_daily}")
    
    print("Checking moneyflow...")
    df_mf = load_parquet(RAW_MONEYFLOW, columns=['ts_code', 'trade_date'])
    dup_mf = df_mf.duplicated(subset=['ts_code', 'trade_date']).sum()
    print(f"Moneyflow duplicates: {dup_mf}")
    
    if dup_mf > 0:
        print("Example duplicates in moneyflow:")
        print(df_mf[df_mf.duplicated(subset=['ts_code', 'trade_date'], keep=False)].head())

if __name__ == "__main__":
    check_duplicates()
