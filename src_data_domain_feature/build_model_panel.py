import polars as pl
from config import (
    FACTOR_READY_DIR,
    MODEL_DATA_DIR
)
import logging

logger = logging.getLogger(__name__)

def load_and_dedup(path):
    """
    Load parquet and deduplicate by ts_code/trade_date.
    Keep the last record if duplicates exist.
    """
    if not path.exists():
        logger.warning(f"Missing {path}, skipping")
        return None
        
    logger.info(f"Loading {path.name}...")
    try:
        # Use scan_parquet for lazy evaluation if memory is tight, 
        # but here we need to dedup so read is fine for 15-80m rows in Polars
        df = pl.read_parquet(path)
        
        # Check unique count
        n_rows = df.height
        n_unique = df.select(['ts_code', 'trade_date']).n_unique()
        
        if n_rows > n_unique:
            logger.warning(f"{path.name} has {n_rows - n_unique} duplicates. Deduplicating...")
            # Keep last observation (assuming later data is more correct/updated)
            df = df.unique(subset=['ts_code', 'trade_date'], keep='last')
            
        return df
    except Exception as e:
        logger.error(f"Error loading {path}: {e}")
        return None

def build_model_panel():
    logger.info("Building Model Panel (Polars optimized)...")
    
    # 1. Load All Features
    # Domain A (Base)
    path_a = FACTOR_READY_DIR / "feature_A_price_volume.parquet"
    df_a = load_and_dedup(path_a)
    
    if df_a is None:
        logger.error("Base feature A missing! Aborting.")
        return
        
    # Domain B
    path_b = FACTOR_READY_DIR / "feature_B_moneyflow.parquet"
    df_b = load_and_dedup(path_b)
    
    # Domain C
    path_c = FACTOR_READY_DIR / "feature_C_chip.parquet"
    df_c = load_and_dedup(path_c)
    
    # Domain E
    path_e = FACTOR_READY_DIR / "feature_E_intraday_summary.parquet"
    df_e = load_and_dedup(path_e)
    
    # Domain D (Model)
    path_d = MODEL_DATA_DIR / "model_domain_D_fundamental.parquet"
    df_d = load_and_dedup(path_d)
    
    # 2. Merge
    logger.info("Merging features...")
    
    # Start with A
    df = df_a
    
    # Left joins
    if df_b is not None:
        df = df.join(df_b, on=['ts_code', 'trade_date'], how='left')
        
    if df_c is not None:
        df = df.join(df_c, on=['ts_code', 'trade_date'], how='left')
        
    if df_e is not None:
        df = df.join(df_e, on=['ts_code', 'trade_date'], how='left')
        
    if df_d is not None:
        df = df.join(df_d, on=['ts_code', 'trade_date'], how='left')
        
    # 3. Save
    out_path = MODEL_DATA_DIR / "model_all_domains_daily.parquet"
    logger.info(f"Saving merged panel to {out_path}...")
    df.write_parquet(out_path)
    
    # Also save train panel
    train_path = MODEL_DATA_DIR / "model_train_panel.parquet"
    logger.info(f"Saving train panel to {train_path}...")
    df.write_parquet(train_path)
    
    logger.info("Model Panel construction complete.")

if __name__ == "__main__":
    build_model_panel()
