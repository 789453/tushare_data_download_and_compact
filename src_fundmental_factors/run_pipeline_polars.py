import polars as pl
import os
from tqdm import tqdm
from joblib import Parallel, delayed
from data_loader_polars import DataLoaderPolars
from preprocess_polars import preprocess_and_merge
from factor_library_daily_polars import add_daily_factors
from factor_library_quarter_polars import get_fina_cols_polars, add_quarterly_factors, add_composite_factors
from transforms_polars import neutralize_numpy

def process_date_group(date_df):
    """
    Process a single date group for neutralization.
    Must be defined at module level for joblib pickling.
    """
    # Calculate ep_ttm_neu = resid(ep_ttm ~ log_size + l1_name)
    # We can add more neutralized factors here if needed
    try:
        neu_series = neutralize_numpy(date_df, 'ep_ttm', 'l1_name', 'log_size')
        return date_df.with_columns(neu_series.alias('ep_ttm_neu'))
    except:
        return date_df.with_columns(pl.lit(None).cast(pl.Float64).alias('ep_ttm_neu'))

def run_pipeline():
    print("Starting Optimized Polars Factor Pipeline...")
    loader = DataLoaderPolars()
    
    # 1. Load Data (Lazy)
    print("Loading datasets (Lazy)...")
    daily_lf = loader.load_daily_basic()
    ind_lf = loader.load_industry()
    fina_lf = loader.load_fina_indicator()
    
    # 2. Preprocess & Merge (Lazy)
    print("Building computation graph: Preprocess & Merge...")
    fina_cols = get_fina_cols_polars()
    merged_lf = preprocess_and_merge(daily_lf, ind_lf, fina_lf, fina_cols)
    
    # 3. Add Factors (Lazy)
    print("Building computation graph: Daily & Quarterly Factors...")
    # Add daily factors
    lf = add_daily_factors(merged_lf)
    # Add quarterly factors
    lf = add_quarterly_factors(lf)
    # Add composite factors
    lf = add_composite_factors(lf)
    
    # 4. Determine Date Range for Batching
    print("Determining date range for batch processing...")
    # Fetch unique years
    years = daily_lf.select(
        pl.col('trade_date').str.slice(0, 4).unique().sort()
    ).collect().to_series().to_list()
    
    print(f"Processing years: {years}")
    
    output_dir = r"d:\Trading\data_ever_26_3_14\data\Fundmental_data"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "fundamental_factors.parquet")
    
    # We will process year by year to manage memory and provide progress
    all_processed_paths = []
    
    for year in tqdm(years, desc="Batching by Year"):
        year_lf = lf.filter(pl.col('date').dt.year() == int(year))
        
        # Collect year data
        try:
            year_df = year_lf.collect(streaming=True)
        except:
            year_df = year_lf.collect()
            
        if year_df.is_empty():
            continue
            
        # 5. Neutralization (Eager & Parallel for the year)
        date_groups = year_df.partition_by("date", maintain_order=True)
        
        # Run parallel neutralization for this year
        processed_year_dfs = Parallel(n_jobs=-1)(
            delayed(process_date_group)(group) 
            for group in date_groups
        )
        
        if not processed_year_dfs:
            continue
            
        year_final_df = pl.concat(processed_year_dfs)
        
        # Save temporary year file to avoid memory bloat if we were to concat all
        temp_path = os.path.join(output_dir, f"factors_{year}.parquet")
        year_final_df.write_parquet(temp_path)
        all_processed_paths.append(temp_path)
        
    # 6. Final Merge of Year Files
    print("Merging year-batches into final output...")
    # We can use scan_parquet on multiple files and collect
    final_lf = pl.scan_parquet(os.path.join(output_dir, "factors_*.parquet"))
    final_lf.sink_parquet(output_path)
    
    # Cleanup temp files
    print("Cleaning up temporary batch files...")
    for p in all_processed_paths:
        try:
            os.remove(p)
        except:
            pass
            
    print(f"Pipeline completed successfully! Final file saved to {output_path}")

if __name__ == "__main__":
    run_pipeline()
