import numpy as np
import pandas as pd
from tqdm import tqdm
from config import (
    RAW_DAILY, 
    RAW_DAILY_BASIC, 
    DOMAIN_DATA_DIR, 
    FACTOR_READY_DIR,
    EPSILON
)
from utils_io import load_parquet, save_parquet
from utils_clean import safe_div, standardize_date, winsorize_series, check_ohlc_validity
import logging

logger = logging.getLogger(__name__)

def build_domain_A():
    logger.info("Building Domain A: Price & Volume...")
    
    # 1. Load Data
    cols_daily = ['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'pre_close']
    df_daily = load_parquet(RAW_DAILY, columns=cols_daily)
    df_daily = df_daily.drop_duplicates(subset=['ts_code', 'trade_date'], keep='last')
    
    cols_basic = ['ts_code', 'trade_date', 'turnover_rate_f', 'volume_ratio']
    df_basic = load_parquet(RAW_DAILY_BASIC, columns=cols_basic)
    df_basic = df_basic.drop_duplicates(subset=['ts_code', 'trade_date'], keep='last')
    
    df_daily['trade_date'] = standardize_date(df_daily['trade_date'])
    df_basic['trade_date'] = standardize_date(df_basic['trade_date'])
    
    df = pd.merge(df_daily, df_basic, on=['ts_code', 'trade_date'], how='left')
    
    # 3. Validity Check
    logger.info("Checking OHLC validity...")
    price_floor = 0.05
    valid_mask = check_ohlc_validity(df, price_floor=price_floor)
    invalid_count = (~valid_mask).sum()
    if invalid_count > 0:
        logger.warning(f"Found {invalid_count} invalid OHLC rows. Setting features to NaN for these rows.")
        
    df['ohlc_invalid_flag'] = (~valid_mask).astype(np.int8)
    
    def safe_div_series(n, d, fill_val=np.nan):
        return safe_div(n, d, fill_value=fill_val)

    # --- 1) Returns and Gaps ---
    # A1. ret_cc_1d
    df['ret_cc_1d_raw'] = safe_div_series(df['close'] - df['pre_close'], df['pre_close'])
    
    # New suspect flags: 
    # 1. Market extreme: > 25% or < -25% (unlikely for index/stocks unless new/ST)
    # 2. Likely dirty: > 50% or < -50% (almost certainly dirty or split/dividend missing)
    # 3. Tiny preclose: pre_close < 0.1
    
    df['ret_cc_1d_market_extreme_flag'] = ((df['ret_cc_1d_raw'] > 0.25) | (df['ret_cc_1d_raw'] < -0.25)).astype(np.int8)
    df['ret_cc_1d_likely_dirty_flag'] = ((df['ret_cc_1d_raw'] > 0.50) | (df['ret_cc_1d_raw'] < -0.50)).astype(np.int8)
    df['tiny_preclose_flag'] = (df['pre_close'] < 0.1).astype(np.int8)
    
    # Combined suspect flag for compatibility
    df['ret_cc_1d_suspect_flag'] = (df['ret_cc_1d_market_extreme_flag'] | df['tiny_preclose_flag']).astype(np.int8)
    
    df['ret_cc_1d_robust'] = winsorize_series(df['ret_cc_1d_raw'], limits=(5.0, 0.0), strategy='sigma')
    
    # A2. ret_oc_1d
    df['ret_oc_1d_raw'] = safe_div_series(df['close'] - df['open'], df['open'])
    
    df['ret_oc_1d_market_extreme_flag'] = ((df['ret_oc_1d_raw'] > 0.25) | (df['ret_oc_1d_raw'] < -0.25)).astype(np.int8)
    df['ret_oc_1d_likely_dirty_flag'] = ((df['ret_oc_1d_raw'] > 0.50) | (df['ret_oc_1d_raw'] < -0.50)).astype(np.int8)
    df['tiny_open_flag'] = (df['open'] < 0.1).astype(np.int8)
    
    df['ret_oc_1d_suspect_flag'] = (df['ret_oc_1d_market_extreme_flag'] | df['tiny_open_flag']).astype(np.int8)
    
    df['ret_oc_1d_robust'] = winsorize_series(df['ret_oc_1d_raw'], limits=(5.0, 0.0), strategy='sigma')
    
    # A3. gap_open
    df['gap_open_raw'] = safe_div_series(df['open'] - df['pre_close'], df['pre_close'])
    df['gap_open_robust'] = winsorize_series(df['gap_open_raw'], limits=(5.0, 0.0), strategy='sigma')
    
    # --- 2) K-line shapes ---
    # A4. intraday_range
    df['intraday_range_raw'] = safe_div_series(df['high'] - df['low'], df['pre_close'])
    df['intraday_range_robust'] = winsorize_series(df['intraday_range_raw'], limits=(5.0, 0.0), strategy='sigma')
    
    # A5/A6. Shadow Ratios
    range_hl = df['high'] - df['low']
    body_top = np.maximum(df['open'], df['close'])
    body_bot = np.minimum(df['open'], df['close'])
    
    # New: Range too small flag (amplitude < 0.5%)
    # If range is very small, shadow ratios are unstable.
    df['range_too_small_flag'] = (range_hl < (df['pre_close'] * 0.005)).astype(np.int8)
    
    # Calculate raw
    df['upper_shadow_ratio_raw'] = safe_div_series(df['high'] - body_top, range_hl)
    df['lower_shadow_ratio_raw'] = safe_div_series(body_bot - df['low'], range_hl)
    
    # Valid condition: valid OHLC and range not too small
    shadow_valid_mask = valid_mask & (df['range_too_small_flag'] == 0)
    
    # If invalid, set to NaN? Or keep raw?
    # Recommendation: "When range too small, set NaN"
    df.loc[~shadow_valid_mask, ['upper_shadow_ratio_raw', 'lower_shadow_ratio_raw']] = np.nan
    
    # Only valid when valid_mask is True for others
    df.loc[~valid_mask, ['ret_cc_1d_raw', 'ret_oc_1d_raw', 'gap_open_raw', 'intraday_range_raw']] = np.nan
    
    # --- 3) Volume and Turnover ---
    # A7. turnover_free
    df['turnover_free_raw'] = df['turnover_rate_f'] / 100.0
    df['turnover_free_log'] = np.where(df['turnover_free_raw'] > 0, np.log1p(df['turnover_free_raw']), np.nan)
    
    # A8. volume_ratio
    df['volume_ratio_raw'] = df['volume_ratio']
    # If 0 or missing, it should be NaN for log
    df['volume_ratio_ln'] = np.where(df['volume_ratio'] > 0, np.log1p(df['volume_ratio']), np.nan)
    
    # Final check for infs
    feat_cols = [
        'ret_cc_1d_raw', 'ret_cc_1d_robust', 'ret_oc_1d_raw', 'ret_oc_1d_robust',
        'gap_open_raw', 'gap_open_robust', 'intraday_range_raw', 'intraday_range_robust',
        'upper_shadow_ratio_raw', 'lower_shadow_ratio_raw',
        'turnover_free_raw', 'turnover_free_log', 'volume_ratio_raw', 'volume_ratio_ln'
    ]
    df[feat_cols] = df[feat_cols].replace([np.inf, -np.inf], np.nan)
        
    # Save Domain Table
    domain_path = DOMAIN_DATA_DIR / "domain_price_volume_daily.parquet"
    save_parquet(df, domain_path)
    
    # Save Feature Table
    feature_cols = [
        'ts_code', 'trade_date',
        'ret_cc_1d_raw', 'ret_cc_1d_robust', 'ret_oc_1d_raw', 'ret_oc_1d_robust',
        'gap_open_raw', 'gap_open_robust', 'intraday_range_raw', 'intraday_range_robust',
        'upper_shadow_ratio_raw', 'lower_shadow_ratio_raw',
        'turnover_free_raw', 'turnover_free_log', 'volume_ratio_raw', 'volume_ratio_ln',
        'ret_cc_1d_suspect_flag', 'ret_oc_1d_suspect_flag', 'ohlc_invalid_flag',
        'ret_cc_1d_market_extreme_flag', 'ret_cc_1d_likely_dirty_flag', 'tiny_preclose_flag',
        'ret_oc_1d_market_extreme_flag', 'ret_oc_1d_likely_dirty_flag', 'tiny_open_flag',
        'range_too_small_flag'
    ]
    feature_path = FACTOR_READY_DIR / "feature_A_price_volume.parquet"
    save_parquet(df[feature_cols], feature_path)
    
    logger.info("Domain A processing complete.")

if __name__ == "__main__":
    build_domain_A()
