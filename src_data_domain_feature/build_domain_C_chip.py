import numpy as np
import pandas as pd
from config import (
    RAW_DAILY,
    RAW_CYQ_PERF,
    DOMAIN_DATA_DIR,
    FACTOR_READY_DIR,
    EPSILON,
    START_DATE_C
)
from utils_io import load_parquet, save_parquet
from utils_clean import standardize_date, winsorize_series, clip_by_bounds, safe_div
import logging

logger = logging.getLogger(__name__)

def build_domain_C():
    logger.info("Building Domain C: Chip Distribution (CYQ)...")
    
    # 1. Load Data
    cols_cyq = [
        'ts_code', 'trade_date', 
        'cost_5pct', 'cost_15pct', 'cost_50pct', 
        'cost_85pct', 'cost_95pct', 'weight_avg', 
        'winner_rate', 'his_low', 'his_high'
    ]
    df_cyq = load_parquet(RAW_CYQ_PERF, columns=cols_cyq)
    df_cyq = df_cyq.drop_duplicates(subset=['ts_code', 'trade_date'], keep='last')
    
    df_cyq['trade_date'] = standardize_date(df_cyq['trade_date'])
    df_cyq = df_cyq[df_cyq['trade_date'] >= START_DATE_C]
    
    cols_daily = ['ts_code', 'trade_date', 'close']
    df_daily = load_parquet(RAW_DAILY, columns=cols_daily)
    df_daily = df_daily.drop_duplicates(subset=['ts_code', 'trade_date'], keep='last')
    df_daily['trade_date'] = standardize_date(df_daily['trade_date'])
    
    df_daily = df_daily[df_daily['trade_date'] >= START_DATE_C]
    df = pd.merge(df_daily, df_cyq, on=['ts_code', 'trade_date'], how='left')
    
    # Filter for data >= 2018-01-01
    df = df[df['trade_date'] >= '20180101'].copy()
    logger.info(f"Filtered data to 2018+, remaining rows: {len(df)}")
    
    # Helper for safe division
    def safe_div_series(n, d, fill_val=np.nan):
        return safe_div(n, d, fill_value=fill_val)
        
    # --- 1) Base Fields Validation ---
    
    # Cost monotonicity and missing
    cost_cols = ['cost_5pct', 'cost_15pct', 'cost_50pct', 'cost_85pct', 'cost_95pct']
    df['chip_cost_any_missing'] = df[cost_cols].isna().any(axis=1).astype(np.int8)
    
    df['chip_cost_nonpositive_flag'] = (df[cost_cols] <= 0).any(axis=1).astype(np.int8)
    
    monotonic_ok = (df['cost_5pct'] <= df['cost_15pct']) & \
                   (df['cost_15pct'] <= df['cost_50pct']) & \
                   (df['cost_50pct'] <= df['cost_85pct']) & \
                   (df['cost_85pct'] <= df['cost_95pct'])
    df['chip_cost_monotonic_ok'] = monotonic_ok.astype(np.int8)
    
    # Valid condition for chip cost derivatives
    cost_valid_mask = (df['chip_cost_any_missing'] == 0) & (df['chip_cost_nonpositive_flag'] == 0) & monotonic_ok
    
    # Weight avg validation
    weight_avg_valid = df['weight_avg'].notna() & (df['weight_avg'] > 0)
    
    # Winner rate
    df['winner_rate_raw'] = df['winner_rate']
    df['winner_rate_out_of_domain_flag'] = ((df['winner_rate_raw'] < 0) | (df['winner_rate_raw'] > 100)).astype(np.int8)
    df['winner_rate_capped'] = df['winner_rate_raw'].clip(0.0, 100.0)
    
    # His low/high
    df['hist_range_zero_flag'] = (df['his_high'] == df['his_low']).astype(np.int8)
    
    # --- 2) Derived Fields ---
    
    # C1. close_vs_cost50
    df['close_vs_cost50_raw'] = safe_div_series(df['close'] - df['cost_50pct'], df['cost_50pct'])
    df['close_vs_cost50_den_invalid_flag'] = (~cost_valid_mask).astype(np.int8)
    df['close_vs_cost50_valid'] = np.where(cost_valid_mask, df['close_vs_cost50_raw'], np.nan)
    df['close_vs_cost50_extreme_flag'] = (df['close_vs_cost50_valid'].abs() > 3.0).astype(np.int8)
    df['close_vs_cost50_robust'] = winsorize_series(df['close_vs_cost50_valid'], limits=(5.0, 0.0), strategy='sigma')
    
    # C2. close_vs_weight_avg
    df['close_vs_weight_avg_raw'] = safe_div_series(df['close'] - df['weight_avg'], df['weight_avg'])
    df['close_vs_weight_avg_valid'] = np.where(weight_avg_valid, df['close_vs_weight_avg_raw'], np.nan)
    df['close_vs_weight_avg_robust'] = winsorize_series(df['close_vs_weight_avg_valid'], limits=(5.0, 0.0), strategy='sigma')
    
    # C3/C4. chip_width
    df['chip_width_95_5_raw'] = safe_div_series(df['cost_95pct'] - df['cost_5pct'], df['cost_50pct'])
    df['chip_width_95_5_valid'] = np.where(cost_valid_mask, df['chip_width_95_5_raw'], np.nan)
    df['chip_width_extreme_flag'] = (df['chip_width_95_5_valid'] > 5.0).astype(np.int8)
    
    df['chip_width_85_15_raw'] = safe_div_series(df['cost_85pct'] - df['cost_15pct'], df['cost_50pct'])
    df['chip_width_85_15_valid'] = np.where(cost_valid_mask, df['chip_width_85_15_raw'], np.nan)
    
    # C5/C6. overhang / support
    df['overhang_95_raw'] = safe_div_series(df['cost_95pct'] - df['close'], df['close'])
    df['overhang_95_valid'] = np.where(cost_valid_mask, df['overhang_95_raw'], np.nan)
    df['overhang_95_outlier_flag'] = (df['overhang_95_valid'].abs() > 3.0).astype(np.int8)
    
    df['support_5_raw'] = safe_div_series(df['close'] - df['cost_5pct'], df['close'])
    df['support_5_valid'] = np.where(cost_valid_mask, df['support_5_raw'], np.nan)
    df['support_5_outlier_flag'] = (df['support_5_valid'].abs() > 3.0).astype(np.int8)
    
    # C7. winner_rate_pct
    df['winner_rate_pct_raw'] = df['winner_rate_raw'] / 100.0
    df['winner_rate_pct_capped'] = df['winner_rate_capped'] / 100.0
    
    # C8. price_pos_hist
    hist_rng = df['his_high'] - df['his_low']
    df['price_pos_hist_raw'] = safe_div_series(df['close'] - df['his_low'], hist_rng)
    
    # New flags for price_pos_hist
    df['hist_range_small_flag'] = (hist_rng < 0.01).astype(np.int8)
    df['his_low_nonpositive_flag'] = (df['his_low'] <= 0).astype(np.int8)
    
    # Strict range check [-0.01, 1.01] to allow float error
    df['price_pos_hist_out_of_domain_flag'] = ((df['price_pos_hist_raw'] < -0.01) | (df['price_pos_hist_raw'] > 1.01)).astype(np.int8)
    
    # Valid condition: range not zero, range not too small, result not out of domain
    hist_valid_mask = (df['hist_range_zero_flag'] == 0) & \
                      (df['hist_range_small_flag'] == 0) & \
                      (df['price_pos_hist_out_of_domain_flag'] == 0)
                      
    df['price_pos_hist_valid'] = np.where(hist_valid_mask, df['price_pos_hist_raw'], np.nan)
    
    # Save Domain Table
    domain_path = DOMAIN_DATA_DIR / "domain_chip_daily.parquet"
    save_parquet(df, domain_path)
    
    # Save Feature Table
    feature_cols = [
        'ts_code', 'trade_date',
        'close_vs_cost50_valid', 'close_vs_cost50_robust',
        'close_vs_weight_avg_valid', 'close_vs_weight_avg_robust',
        'chip_width_95_5_valid', 'chip_width_85_15_valid',
        'overhang_95_valid', 'support_5_valid',
        'winner_rate_pct_raw', 'winner_rate_pct_capped',
        'price_pos_hist_valid',
        'chip_cost_monotonic_ok', 'chip_cost_any_missing', 'chip_cost_nonpositive_flag',
        'winner_rate_out_of_domain_flag', 'hist_range_zero_flag',
        'hist_range_small_flag', 'his_low_nonpositive_flag', 'price_pos_hist_out_of_domain_flag',
        'close_vs_cost50_den_invalid_flag', 'close_vs_cost50_extreme_flag',
        'chip_width_extreme_flag', 'overhang_95_outlier_flag', 'support_5_outlier_flag'
    ]
    
    feature_path = FACTOR_READY_DIR / "feature_C_chip.parquet"
    save_parquet(df[feature_cols], feature_path)
    
    logger.info("Domain C processing complete.")

if __name__ == "__main__":
    build_domain_C()
