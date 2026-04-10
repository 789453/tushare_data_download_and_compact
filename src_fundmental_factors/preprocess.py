import pandas as pd
import numpy as np

def match_industry(daily_df, ind_df):
    """
    Match daily dataframe with industry classification at point in time.
    daily_df: needs 'ts_code' and 'trade_date'
    ind_df: needs 'ts_code', 'in_date', 'out_date', 'l1_name', 'l2_name', 'l3_name'
    """
    # Sort for merge_asof if needed, but since intervals can overlap if a stock changes industry,
    # SQL-like inequality join is better. Given the size, we can do this efficiently.
    print("Matching industry mappings...")
    # First, let's optimize by just doing an inner join on ts_code, then filter
    daily_codes = daily_df[['ts_code', 'trade_date']].copy()
    merged = pd.merge(daily_codes, ind_df[['ts_code', 'in_date', 'out_date', 'l1_name', 'l2_name', 'l3_name']], on='ts_code', how='left')
    
    # Filter valid dates
    valid = merged[(merged['trade_date'] >= merged['in_date']) & (merged['trade_date'] < merged['out_date'])]
    # If a stock has multiple valid industries on the same day (rare but possible), drop duplicates
    valid = valid.drop_duplicates(subset=['ts_code', 'trade_date'], keep='last')
    
    # Join back to daily_df
    res = pd.merge(daily_df, valid[['ts_code', 'trade_date', 'l1_name', 'l2_name', 'l3_name']], on=['ts_code', 'trade_date'], how='left')
    return res

def merge_fina_data(daily_df, fina_df, fina_cols):
    """
    Merge daily_df with fina_df using point-in-time logic (merge_asof).
    fina_df should be applied as of ann_date <= trade_date.
    fina_cols: list of columns to extract from fina_df along with ts_code and ann_date.
    """
    print("Merging financial data...")
    # Clean fina_df
    fina_sub = fina_df[['ts_code', 'ann_date', 'end_date'] + [c for c in fina_cols if c in fina_df.columns]].copy()
    fina_sub = fina_sub.dropna(subset=['ann_date'])
    fina_sub['ann_date'] = pd.to_datetime(fina_sub['ann_date'], errors='coerce')
    fina_sub = fina_sub.dropna(subset=['ann_date'])
    
    # Sort by ts_code, ann_date, end_date to keep the latest report if announced on same day
    fina_sub = fina_sub.sort_values(['ts_code', 'ann_date', 'end_date'])
    fina_sub = fina_sub.drop_duplicates(subset=['ts_code', 'ann_date'], keep='last')
    
    # Sort by ann_date for merge_asof
    fina_sub = fina_sub.sort_values('ann_date')
    
    # For merge_asof, trade_date must also be datetime
    daily_df_dates = pd.to_datetime(daily_df['trade_date'])
    daily_df['trade_date_dt'] = daily_df_dates
    daily_df = daily_df.sort_values('trade_date_dt')
    
    # Group by ts_code is not supported directly in merge_asof with exact match unless using by='ts_code'
    merged = pd.merge_asof(
        daily_df,
        fina_sub,
        left_on='trade_date_dt',
        right_on='ann_date',
        by='ts_code',
        direction='backward'
    )
    
    merged = merged.drop(columns=['trade_date_dt', 'ann_date'])
    return merged
