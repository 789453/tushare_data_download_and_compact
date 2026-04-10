import polars as pl
import numpy as np
from transforms_polars import (
    ind_rank, ts_lag, ts_roc, ts_zscore, neutralize_numpy
)

def add_daily_factors(lf: pl.LazyFrame) -> pl.LazyFrame:
    """
    Add daily fundamental and trading factors (Lazy execution).
    """
    # 1. Base Valuation & Ratios
    # ep_ttm, bp, sp_ttm, div_ttm_val
    # turn_f, vol_ratio, log_size, ff_ratio
    
    # Using with_columns for parallel execution
    lf = lf.with_columns([
        (1.0 / pl.col('pe_ttm')).alias('ep_ttm'),
        (1.0 / pl.col('pb')).alias('bp'),
        (1.0 / pl.col('ps_ttm')).alias('sp_ttm'),
        (pl.col('dv_ttm') / 100.0).alias('div_ttm_val'),
        
        pl.col('turnover_rate_f').log1p().alias('turn_f'),
        pl.col('volume_ratio').log1p().alias('vol_ratio'),
        pl.col('circ_mv').log().alias('log_size'),
        (pl.col('free_share') / pl.col('float_share')).alias('ff_ratio')
    ])
    
    # 2. Time-series derived factors
    # Need sorting by date within group usually, but if data is globally sorted by ts_code, date, we can just use shift over ts_code
    # Polars over('ts_code') operations:
    # ts_lag, ts_roc, ts_zscore
    
    # We must ensure order within group for shift/rolling.
    # But lazy frame sort is expensive?
    # Actually if we trust input is sorted, we can use set_sorted? No, over() partitions.
    # Sort within over is implicit? No.
    # Best practice: sort the whole LF by ts_code, date before this function.
    
    lf = lf.with_columns([
        ts_lag('ep_ttm', 1).over('ts_code').alias('ep_ttm_lag1'),
        ts_lag('ep_ttm', 5).over('ts_code').alias('ep_ttm_lag5'),
        ts_lag('ep_ttm', 20).over('ts_code').alias('ep_ttm_lag20'),
        
        (pl.col('ep_ttm') / ts_lag('ep_ttm', 20).over('ts_code') - 1.0).alias('ep_ttm_chg20'),
        
        ts_roc('turn_f', 5).over('ts_code').alias('turn_f_chg5'),
        ts_roc('pb', 20).over('ts_code').alias('pb_compress_20'),
        (pl.col('pe_ttm') / ts_lag('pe_ttm', 20).over('ts_code') - 1.0).alias('pe_re_rate_20'),
        
        ts_zscore('turn_f', 20).over('ts_code').alias('turn_f_z20'),
        ts_zscore('vol_ratio', 20).over('ts_code').alias('vol_ratio_z20')
    ])
    
    # 3. Cross-sectional Ranks (Simple ones using over(date, group))
    # ind_rank returns an expression with over inside? No, my implementation returned expression using over.
    # ind_rank(col, ind_col) -> count().over(ind_col), rank().over(ind_col)
    # We need to apply this per day.
    # So we wrap in .over('date', 'l2_name')? No, ind_rank implementation uses over(ind_col).
    # If we call it on the whole dataframe, it ranks over ALL dates for that industry. That's wrong.
    # We need rank within (date, industry).
    # So ind_rank implementation in transforms_polars should be:
    # rank().over('date', ind_col)
    
    # Let's redefine ind_rank call here to be explicit
    
    lf = lf.with_columns([
        (pl.col('ep_ttm').rank("ordinal").over(['date', 'l2_name']) / pl.col('ep_ttm').count().over(['date', 'l2_name'])).alias('ep_ttm_rank_ind_l2'),
        (pl.col('bp').rank("ordinal").over(['date', 'l2_name']) / pl.col('bp').count().over(['date', 'l2_name'])).alias('bp_rank_ind_l2'),
        (pl.col('div_ttm_val').rank("ordinal").over(['date', 'l1_name']) / pl.col('div_ttm_val').count().over(['date', 'l1_name'])).alias('div_ttm_rank_ind_l1'),
        (pl.col('turn_f').rank("ordinal").over(['date', 'l2_name']) / pl.col('turn_f').count().over(['date', 'l2_name'])).alias('turn_f_rank_ind_l2'),
        
        (pl.col('turn_f_chg5').rank("ordinal").over(['date', 'l2_name']) / pl.col('turn_f_chg5').count().over(['date', 'l2_name'])).alias('turn_f_chg5_ind_rank'),
        (pl.col('pb_compress_20').rank("ordinal").over(['date', 'l2_name']) / pl.col('pb_compress_20').count().over(['date', 'l2_name'])).alias('pb_compress_20_ind_rank')
    ])
    
    # 4. Complex Daily Factors (that don't need regression)
    # crowding = z(turn_f) + z(vol_ratio)
    # anti_crowding = -crowding
    # value_recovery = bp_rank - turn_f_rank
    
    lf = lf.with_columns([
        (-(pl.col('turn_f_z20').fill_null(0) + pl.col('vol_ratio_z20').fill_null(0))).alias('anti_crowding'),
        (pl.col('bp_rank_ind_l2') - pl.col('turn_f_rank_ind_l2')).alias('value_recovery')
    ])
    
    return lf

def add_neutralized_factors(df: pl.DataFrame) -> pl.DataFrame:
    """
    Add neutralized factors using map_groups (Eager execution).
    This handles cross-sectional regression per date.
    """
    # Columns to neutralize: ep_ttm
    # Target: ep_ttm_neu
    # Regress ep_ttm on log_size + l1_name dummies
    
    # We can use map_groups on 'date'
    # Define schema for output?
    # map_groups returns a DataFrame.
    # It's better to just calculate the specific column and join back?
    # Or just use with_columns with a custom function that returns a Series of the same length for the group.
    
    # But map_groups applies function to each group.
    # We want to add a column.
    
    # Using transform-like operation in Polars eager:
    # df.group_by('date').map_groups(lambda g: g.with_columns(...))
    
    print("Neutralizing ep_ttm...")
    
    # Define a wrapper for the group function
    def process_group(g):
        # returns the group with new column
        res = neutralize_numpy(g, 'ep_ttm', 'l1_name', 'circ_mv')
        return g.with_columns(res.alias('ep_ttm_neu'))

    # This might be slow if many dates.
    # Parallelism is handled by map_groups if we set strategy?
    # map_groups is sequential in Python usually unless using ThreadPoolExecutor manually?
    # Actually Polars `map_groups` executes in parallel if `is_elementwise` is false? No.
    # We will use simple loop if map_groups is slow, or rely on joblib in main pipeline.
    # But let's stick to Polars API.
    
    # Since we need to return the whole dataframe with new column,
    # map_groups is appropriate.
    
    return df.group_by('date', maintain_order=True).map_groups(process_group)

