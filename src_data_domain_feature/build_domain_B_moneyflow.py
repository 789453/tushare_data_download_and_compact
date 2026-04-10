import numpy as np
import pandas as pd
from config import (
    RAW_DAILY,
    RAW_MONEYFLOW,
    DOMAIN_DATA_DIR,
    FACTOR_READY_DIR,
    EPSILON,
    START_DATE_B
)
from utils_io import load_parquet, save_parquet
from utils_clean import standardize_date, winsorize_series, safe_div
import logging

logger = logging.getLogger(__name__)

def build_domain_B():
    logger.info("Building Domain B: Moneyflow...")
    
    # 1. Load Data
    cols_mf = [
        'ts_code', 'trade_date', 
        'buy_sm_amount', 'sell_sm_amount', 
        'buy_md_amount', 'sell_md_amount',
        'buy_lg_amount', 'sell_lg_amount', 
        'buy_elg_amount', 'sell_elg_amount',
        'net_mf_amount'
    ]
    df_mf = load_parquet(RAW_MONEYFLOW, columns=cols_mf)
    df_mf = df_mf.drop_duplicates(subset=['ts_code', 'trade_date'], keep='last')
    
    df_mf['trade_date'] = standardize_date(df_mf['trade_date'])
    df_mf = df_mf[df_mf['trade_date'] >= START_DATE_B]
    
    cols_daily = ['ts_code', 'trade_date', 'amount']
    df_daily = load_parquet(RAW_DAILY, columns=cols_daily)
    df_daily = df_daily.drop_duplicates(subset=['ts_code', 'trade_date'], keep='last')
    df_daily['trade_date'] = standardize_date(df_daily['trade_date'])
    
    df_daily = df_daily[df_daily['trade_date'] >= START_DATE_B]
    df = pd.merge(df_daily, df_mf, on=['ts_code', 'trade_date'], how='left')
    
    # Helper for safe division
    def safe_div_series(n, d, fill_val=np.nan, min_abs_den=1e-4):
        return safe_div(n, d, fill_value=fill_val, min_abs_den=min_abs_den)
        
    mf_cols = [
        'buy_sm_amount', 'sell_sm_amount',
        'buy_md_amount', 'sell_md_amount',
        'buy_lg_amount', 'sell_lg_amount',
        'buy_elg_amount', 'sell_elg_amount',
        'net_mf_amount'
    ]
    for col in mf_cols:
        if col in df.columns:
            df[col] = df[col] * 10.0
            
    # --- 1) Base Validations & Flags ---
    df['amount_nonpositive_flag'] = (df['amount'] <= 0).astype(np.int8)
    amount_valid = (df['amount'] > 0)
    
    for col in ['buy_sm_amount', 'buy_md_amount', 'buy_lg_amount', 'buy_elg_amount',
                'sell_sm_amount', 'sell_md_amount', 'sell_lg_amount', 'sell_elg_amount']:
        df[f'{col}_missing_flag'] = df[col].isna().astype(np.int8)
        df[f'{col}_zero_flag'] = (df[col] == 0).astype(np.int8)
        df[f'{col}_no_activity_but_traded_flag'] = (amount_valid & (df[col] == 0)).astype(np.int8)
        
    # --- 2) Imbalances ---
    # Define a helper to process imbalance
    def process_imbalance(prefix, buy_col, sell_col):
        net = df[buy_col] - df[sell_col]
        tot = df[buy_col] + df[sell_col]
        
        raw_col = f'{prefix}_raw'
        df[raw_col] = safe_div_series(net, tot)
        
        df[f'{prefix}_missing_input_flag'] = (df[buy_col].isna() | df[sell_col].isna()).astype(np.int8)
        df[f'{prefix}_den_zero_flag'] = (tot == 0).astype(np.int8)
        
        # New: Detailed denominator flags
        df[f'{prefix}_micro_den_flag'] = ((tot > 0) & (tot < 100)).astype(np.int8) # Micro denominator (<1M)
        df[f'{prefix}_small_den_flag'] = ((tot >= 100) & (tot < 1000)).astype(np.int8) # Small denominator (<10M)
        
        # Valid version: only when denominator is valid and inputs are not missing
        # We allow micro denominators in valid, but downstream should filter using the flag if needed.
        valid_mask = (df[f'{prefix}_missing_input_flag'] == 0) & (df[f'{prefix}_den_zero_flag'] == 0)
        df[f'{prefix}_valid'] = np.where(valid_mask, df[raw_col], np.nan)
        
    process_imbalance('imb_sm_amt', 'buy_sm_amount', 'sell_sm_amount')
    process_imbalance('imb_md_amt', 'buy_md_amount', 'sell_md_amount')
    process_imbalance('imb_lg_amt', 'buy_lg_amount', 'sell_lg_amount')
    process_imbalance('imb_elg_amt', 'buy_elg_amount', 'sell_elg_amount')
    
    # --- 3) Relative Amounts ---
    # B5. net_mf_to_amount
    df['net_mf_to_amount_raw'] = safe_div_series(df['net_mf_amount'], df['amount'])
    df['net_mf_to_amount_valid'] = np.where(amount_valid, df['net_mf_to_amount_raw'], np.nan)
    df['net_mf_to_amount_robust'] = winsorize_series(df['net_mf_to_amount_valid'], limits=(5.0, 0.0), strategy='sigma')
    
    # B6. large_buy_share
    # Formula: (buy_lg + buy_elg) / amount
    # If this exceeds 1, it implies moneyflow components > total amount.
    # We should strictly enforce [0, 1] for the valid version.
    large_buy_tot = df['buy_lg_amount'] + df['buy_elg_amount']
    df['large_buy_share_raw'] = safe_div_series(large_buy_tot, df['amount'])
    
    # Check if really out of domain (> 1.01 to allow small float errors)
    df['large_buy_share_out_of_domain_flag'] = ((df['large_buy_share_raw'] < -0.01) | (df['large_buy_share_raw'] > 1.01)).astype(np.int8)
    
    # For valid, we set to NaN if it is clearly out of domain, or clip if it's close?
    # Requirement: "If > 1, valid should be null"
    valid_share_mask = amount_valid & (df['large_buy_share_out_of_domain_flag'] == 0)
    df['large_buy_share_valid'] = np.where(valid_share_mask, df['large_buy_share_raw'].clip(0.0, 1.0), np.nan)
    
    # B7. large_sell_share
    large_sell_tot = df['sell_lg_amount'] + df['sell_elg_amount']
    df['large_sell_share_raw'] = safe_div_series(large_sell_tot, df['amount'])
    
    df['large_sell_share_out_of_domain_flag'] = ((df['large_sell_share_raw'] < -0.01) | (df['large_sell_share_raw'] > 1.01)).astype(np.int8)
    
    valid_sell_share_mask = amount_valid & (df['large_sell_share_out_of_domain_flag'] == 0)
    df['large_sell_share_valid'] = np.where(valid_sell_share_mask, df['large_sell_share_raw'].clip(0.0, 1.0), np.nan)
    
    # B8. flow_divergence
    df['flow_divergence_raw'] = safe_div_series(large_buy_tot - large_sell_tot, df['amount'])
    df['flow_divergence_valid'] = np.where(amount_valid, df['flow_divergence_raw'], np.nan)
    
    # 4. Save Domain Table
    domain_path = DOMAIN_DATA_DIR / "domain_moneyflow_daily.parquet"
    save_parquet(df, domain_path)
    
    # 5. Save Feature Table
    feature_cols = [
        'ts_code', 'trade_date',
        'imb_sm_amt_valid', 'imb_md_amt_valid', 'imb_lg_amt_valid', 'imb_elg_amt_valid',
        'net_mf_to_amount_valid', 'net_mf_to_amount_robust', 
        'large_buy_share_valid', 'large_sell_share_valid',
        'flow_divergence_valid',
        'amount_nonpositive_flag',
        'imb_elg_amt_missing_input_flag', 'imb_elg_amt_den_zero_flag', 
        'imb_elg_amt_micro_den_flag', 'imb_elg_amt_small_den_flag',
        'large_buy_share_out_of_domain_flag', 'large_sell_share_out_of_domain_flag'
    ]
    
    # Add base missing/zero flags for elg
    for col in ['buy_elg_amount', 'sell_elg_amount']:
        feature_cols.extend([f'{col}_missing_flag', f'{col}_zero_flag', f'{col}_no_activity_but_traded_flag'])
        
    feature_path = FACTOR_READY_DIR / "feature_B_moneyflow.parquet"
    save_parquet(df[feature_cols], feature_path)
    
    logger.info("Domain B processing complete.")

if __name__ == "__main__":
    build_domain_B()
