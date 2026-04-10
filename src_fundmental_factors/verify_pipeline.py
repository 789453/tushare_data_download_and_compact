import polars as pl
import os
import sys
from data_loader_polars import DataLoaderPolars
from preprocess_polars import preprocess_and_merge
from factor_library_daily_polars import add_daily_factors
from factor_library_quarter_polars import get_fina_cols_polars, add_quarterly_factors, add_composite_factors

def verify_pipeline():
    print("Starting Verification Pipeline (Sample Run)...")
    loader = DataLoaderPolars()
    
    # 1. Load Data (Lazy) with limit
    print("Loading datasets (Lazy)...")
    # We can't limit parquet scan easily without collecting schema or using row_index?
    # Actually slice(0, N) works on lazyframe.
    
    daily_lf = loader.load_daily_basic().filter(pl.col('trade_date') > '20230101')
    ind_lf = loader.load_industry()
    fina_lf = loader.load_fina_indicator()
    
    # 2. Preprocess & Merge (Lazy)
    print("Building computation graph: Preprocess & Merge...")
    fina_cols = get_fina_cols_polars()
    merged_lf = preprocess_and_merge(daily_lf, ind_lf, fina_lf, fina_cols)
    
    # 3. Add Factors (Lazy)
    print("Building computation graph: Factors...")
    lf = add_daily_factors(merged_lf)
    lf = add_quarterly_factors(lf)
    lf = add_composite_factors(lf)
    
    # 4. Collect Sample
    print("Executing Lazy Graph on sample...")
    try:
        # Collect first 1000 rows to verify schema and computation
        df_sample = lf.head(1000).collect()
        print("Sample collection successful!")
        print(f"Sample shape: {df_sample.shape}")
        print("Sample columns:", df_sample.columns)
        
        # Check for critical columns
        critical_cols = [
            'ep_ttm', 'turn_f_z20', 'roe_dt_ind_rank', 
            'comp_value_quality', 'comp_margin_improvement'
        ]
        missing = [c for c in critical_cols if c not in df_sample.columns]
        if missing:
            print(f"ERROR: Missing critical columns: {missing}")
            sys.exit(1)
        else:
            print("All critical columns present.")
            
        # Check for nulls in composites
        null_counts = df_sample.select([pl.col(c).null_count() for c in critical_cols])
        print("Null counts in sample:")
        print(null_counts)
        
    except Exception as e:
        print(f"Pipeline verification failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    verify_pipeline()
