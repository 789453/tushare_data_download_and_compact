import numpy as np
import pandas as pd
from tqdm import tqdm
from config import (
    RAW_DAILY,
    RAW_DAILY_BASIC,
    MODEL_DATA_DIR,
    DOMAIN_DATA_DIR,
    FACTOR_READY_DIR,
    EPSILON
)
from utils_io import load_parquet, save_parquet
from utils_clean import standardize_date
import logging

logger = logging.getLogger(__name__)

def build_domain_D():
    logger.info("Building Domain D: Fundamental (Model Layer)...")
    
    # 1. Load Data
    cols_basic = [
        'ts_code', 'trade_date', 
        'pe_ttm', 'pb', 'ps_ttm', 'dv_ttm',
        'total_share', 'free_share', 
        'total_mv', 'circ_mv'
    ]
    df_basic = load_parquet(RAW_DAILY_BASIC, columns=cols_basic)
    df_basic = df_basic.drop_duplicates(subset=['ts_code', 'trade_date'], keep='last')
    df_basic['trade_date'] = standardize_date(df_basic['trade_date'])
    
    cols_daily = ['ts_code', 'trade_date']
    df_daily = load_parquet(RAW_DAILY, columns=cols_daily)
    df_daily = df_daily.drop_duplicates(subset=['ts_code', 'trade_date'], keep='last')
    df_daily['trade_date'] = standardize_date(df_daily['trade_date'])
    
    df = pd.merge(df_daily, df_basic, on=['ts_code', 'trade_date'], how='left')
    
    # 3. Calculate Features
    logger.info("Calculating features...")
    
    # --- 1) Valuation Fields ---
    # PE TTM
    df['pe_ttm_raw'] = df['pe_ttm']
    df['pe_ttm_valid_flag'] = (df['pe_ttm'] > 0).astype(np.int8)
    df['pe_ttm_log'] = np.where(df['pe_ttm'] > 0, np.log1p(df['pe_ttm']), np.nan)
    
    # PB
    df['pb_raw'] = df['pb']
    df['pb_valid_flag'] = (df['pb'] > 0).astype(np.int8)
    df['pb_log'] = np.where(df['pb'] > 0, np.log1p(df['pb']), np.nan)
    df['pb_extreme_flag'] = (df['pb'] > 100).astype(np.int8)  # Basic threshold for extreme PB
    
    # PS TTM
    df['ps_ttm_raw'] = df['ps_ttm']
    df['ps_ttm_valid_flag'] = (df['ps_ttm'] > 0).astype(np.int8)
    df['ps_ttm_log'] = np.where(df['ps_ttm'] > 0, np.log1p(df['ps_ttm']), np.nan)
    df['ps_ttm_super_extreme_flag'] = (df['ps_ttm'] > 1000).astype(np.int8)
    
    # DV TTM
    df['dv_ttm_raw'] = df['dv_ttm']
    df['dv_ttm_missing_flag'] = df['dv_ttm'].isna().astype(np.int8)
    df['dv_ttm_zero_flag'] = (df['dv_ttm'] == 0).astype(np.int8)
    
    # --- 2) Scale and Structure ---
    df['total_share_log'] = np.log1p(df['total_share'].clip(lower=0))
    df['free_share_log'] = np.log1p(df['free_share'].clip(lower=0))
    df['total_mv_log'] = np.log1p(df['total_mv'].clip(lower=0))
    df['circ_mv_log'] = np.log1p(df['circ_mv'].clip(lower=0))
    
    # Ratios
    df['free_float_ratio_raw'] = df['free_share'] / (df['total_share'] + EPSILON)
    df['free_float_ratio_capped'] = df['free_float_ratio_raw'].clip(0.0, 1.0)
    
    df['circ_mv_to_total_mv_raw'] = df['circ_mv'] / (df['total_mv'] + EPSILON)
    df['circ_mv_to_total_mv_out_of_domain_flag'] = (df['circ_mv_to_total_mv_raw'] > 1.0).astype(np.int8)
    df['circ_mv_to_total_mv_capped'] = df['circ_mv_to_total_mv_raw'].clip(0.0, 1.0)
    
    # --- 3) Ranking ---
    logger.info("Calculating Ranks...")
    df['pe_ttm_rank_mkt'] = df.groupby('trade_date')['pe_ttm'].rank(pct=True)
    df['pe_ttm_rank_ind'] = df['pe_ttm_rank_mkt'] # Fallback
    
    df['pb_rank_ind'] = df.groupby('trade_date')['pb'].rank(pct=True)
    df['ps_ttm_rank_ind'] = df.groupby('trade_date')['ps_ttm'].rank(pct=True)
    df['dv_ttm_rank_mkt'] = df.groupby('trade_date')['dv_ttm'].rank(pct=True)
    df['mv_rank_mkt'] = df.groupby('trade_date')['total_mv'].rank(pct=True)
    
    # Valuation Compress Score
    df['valuation_compress_score'] = (
        -0.4 * df['pe_ttm_rank_ind'] 
        -0.4 * df['pb_rank_ind'] 
        -0.2 * df['ps_ttm_rank_ind']
    )
    
    # Save Domain Table
    domain_path = DOMAIN_DATA_DIR / "domain_fundamental_daily.parquet"
    save_parquet(df, domain_path)
    
    # Save Feature Table
    feature_cols = [
        'ts_code', 'trade_date',
        'pe_ttm_log', 'pb_log', 'ps_ttm_log', 'dv_ttm_raw',
        'total_share_log', 'free_share_log', 'total_mv_log', 'circ_mv_log',
        'free_float_ratio_capped', 'circ_mv_to_total_mv_capped',
        'pe_ttm_rank_mkt', 'pe_ttm_rank_ind', 'pb_rank_ind', 'ps_ttm_rank_ind',
        'dv_ttm_rank_mkt', 'mv_rank_mkt', 'valuation_compress_score',
        'pe_ttm_valid_flag', 'pb_valid_flag', 'pb_extreme_flag',
        'ps_ttm_valid_flag', 'ps_ttm_super_extreme_flag',
        'dv_ttm_missing_flag', 'dv_ttm_zero_flag',
        'circ_mv_to_total_mv_out_of_domain_flag'
    ]
    feature_path = FACTOR_READY_DIR / "feature_D_fundamental.parquet"
    save_parquet(df[feature_cols], feature_path)
    
    model_path = MODEL_DATA_DIR / "model_domain_D_fundamental.parquet"
    save_parquet(df[feature_cols], model_path)
    
    logger.info("Domain D processing complete.")

if __name__ == "__main__":
    build_domain_D()
