import pandas as pd
import numpy as np

def calculate_ic(df, factor_col, return_col='ret_1'):
    """
    Calculate RankIC and IC for a single factor.
    """
    df_clean = df.dropna(subset=[factor_col, return_col])
    if df_clean.empty:
        return np.nan, np.nan
        
    ic = df_clean.groupby('trade_date').apply(
        lambda x: x[factor_col].corr(x[return_col], method='pearson')
    )
    rank_ic = df_clean.groupby('trade_date').apply(
        lambda x: x[factor_col].corr(x[return_col], method='spearman')
    )
    return ic, rank_ic

def calculate_group_returns(df, factor_col, return_col='ret_1', groups=5):
    """
    Calculate average returns for each group.
    """
    # Create groups
    df = df.copy()
    df['group'] = df.groupby('trade_date')[factor_col].transform(
        lambda x: pd.qcut(x, groups, labels=False, duplicates='drop')
    )
    
    # Calculate return per group per day
    group_ret = df.groupby(['trade_date', 'group'])[return_col].mean().unstack()
    
    # Calculate Long-Short return (Top - Bottom)
    # Assuming group 0 is bottom and group N-1 is top
    # But usually factor can be negative. 
    # Let's assume factor direction is positive (higher is better).
    if (groups - 1) in group_ret.columns and 0 in group_ret.columns:
        group_ret['long_short'] = group_ret[groups-1] - group_ret[0]
        
    return group_ret

def evaluate_factor(df, factor_col, return_cols=['ret_1', 'ret_5', 'ret_20']):
    """
    Comprehensive evaluation of a factor.
    """
    results = {}
    
    for ret_col in return_cols:
        if ret_col not in df.columns:
            continue
            
        print(f"Evaluating {factor_col} against {ret_col}...")
        
        # 1. IC Analysis
        ic, rank_ic = calculate_ic(df, factor_col, ret_col)
        
        ic_mean = ic.mean()
        ic_std = ic.std()
        ic_ir = ic_mean / ic_std if ic_std != 0 else 0
        
        rank_ic_mean = rank_ic.mean()
        rank_ic_std = rank_ic.std()
        rank_ic_ir = rank_ic_mean / rank_ic_std if rank_ic_std != 0 else 0
        
        results[f'{ret_col}_ic_mean'] = ic_mean
        results[f'{ret_col}_ic_ir'] = ic_ir
        results[f'{ret_col}_rank_ic_mean'] = rank_ic_mean
        results[f'{ret_col}_rank_ic_ir'] = rank_ic_ir
        results[f'{ret_col}_ic_series'] = ic
        results[f'{ret_col}_rank_ic_series'] = rank_ic
        
        # 2. Group Analysis
        group_ret = calculate_group_returns(df, factor_col, ret_col)
        results[f'{ret_col}_group_ret'] = group_ret
        
    return results

def prepare_returns(df):
    """
    Calculate future returns.
    Assumes df is sorted by ts_code, trade_date.
    """
    # We need 'close' price. If using adj_close it would be better.
    # If only 'close' is available from daily_basic, use that but be aware of splits.
    # Ideally we need 'adj_factor' from daily to calculate adj_close.
    # Since we only have daily_basic.parquet, let's check if we have close.
    # The prompt mentioned raw_daily.parquet but we only loaded daily_basic.
    # Wait, the prompt says "raw_daily" is "d:\Trading\data_ever_26_3_14\data\Raw_data\daily.parquet" (in doc)
    # But in the user input it says "d:\Trading\data_ever_26_3_14\data\Raw_data\daily_basic.parquet".
    # And "d:\Trading\data_ever_26_3_14\data\Raw_data\index_daily_basic_circ_mv.parquet".
    # We might not have adjusted prices. Using raw close for returns is dangerous due to dividends/splits.
    # However, for this task, we will calculate raw returns and warn.
    # Or, if we can find adj_factor or pre_close.
    # daily_basic usually has 'close'.
    
    print("Calculating future returns...")
    # Using groupby shift to get future returns
    # ret_1 = close_t+1 / close_t - 1
    # Actually we want future return.
    # ret_1 = shift(-1) / current - 1
    
    for k in [1, 5, 20]:
        # shift(-k) means looking k days ahead
        future_close = df.groupby('ts_code')['close'].shift(-k)
        df[f'ret_{k}'] = future_close / df['close'] - 1.0
        
    return df
