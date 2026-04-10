import polars as pl
import os

def preprocess_and_merge(
    daily_lf: pl.LazyFrame,
    ind_lf: pl.LazyFrame,
    fina_lf: pl.LazyFrame,
    fina_cols: list
) -> pl.LazyFrame:
    """
    Preprocess and merge data using Polars join_asof.
    """
    # 1. Prepare Dates
    # daily: trade_date -> Date
    daily_lf = daily_lf.with_columns(
        pl.col('trade_date').str.strptime(pl.Date, "%Y%m%d").alias('date')
    ).sort(['ts_code', 'date'])

    # industry: in_date -> Date, out_date -> Date
    ind_lf = ind_lf.with_columns([
        pl.col('in_date').str.strptime(pl.Date, "%Y%m%d").alias('in_date_dt'),
        pl.col('out_date').fill_null('20991231').str.strptime(pl.Date, "%Y%m%d").alias('out_date_dt')
    ]).sort(['ts_code', 'in_date_dt'])

    # fina: ann_date -> Date
    # Filter fina_cols and keep key cols
    needed_fina = ['ts_code', 'ann_date', 'end_date'] + [c for c in fina_cols if c not in ['ts_code', 'ann_date', 'end_date']]
    # Select existing columns only
    # LazyFrame doesn't know columns until schema is fetched, assume they exist or use selector?
    # Better to rely on caller passing correct cols.
    
    fina_lf = fina_lf.select(
        [pl.col(c) for c in needed_fina]
    ).with_columns(
        pl.col('ann_date').str.strptime(pl.Date, "%Y%m%d", strict=False).alias('ann_date_dt'),
        pl.col('end_date').str.strptime(pl.Date, "%Y%m%d", strict=False).alias('end_date_dt')
    ).filter(
        pl.col('ann_date_dt').is_not_null()
    )

    # De-duplicate fina: sort by ts_code, ann_date, end_date and keep last
    # But lazyframe unique with maintain_order or sort then unique(keep='last')
    # Since we need sorted for join_asof anyway:
    fina_lf = fina_lf.sort(
        ['ts_code', 'ann_date_dt', 'end_date_dt']
    ).unique(
        subset=['ts_code', 'ann_date_dt'],
        keep='last'
    )
    
    # 2. Join Industry (Point-in-Time)
    # Join daily with industry on date >= in_date
    # strategy='backward' matches the nearest previous or equal key
    
    # daily keys: ts_code, date
    # ind keys: ts_code, in_date_dt
    
    # join_asof requires sorting by the 'on' column. 'by' column is grouped.
    
    merged = daily_lf.join_asof(
        ind_lf,
        left_on='date',
        right_on='in_date_dt',
        by='ts_code',
        strategy='backward'
    )

    # Filter invalid industry (date >= out_date)
    # merged will have in_date_dt from industry.
    # Check if date < out_date_dt
    merged = merged.filter(
        pl.col('date') < pl.col('out_date_dt')
    )

    # 3. Join Financial Data (Point-in-Time)
    # Join daily with fina on date >= ann_date
    
    merged = merged.join_asof(
        fina_lf,
        left_on='date',
        right_on='ann_date_dt',
        by='ts_code',
        strategy='backward'
    )
    
    # Fill industry nulls
    merged = merged.with_columns([
        pl.col('l1_name').fill_null('Unknown'),
        pl.col('l2_name').fill_null('Unknown'),
        pl.col('l3_name').fill_null('Unknown')
    ])
    
    # Convert financial columns to float
    # Polars usually infers schema, but better safe
    # Using cast(pl.Float64)
    # fina_cols excluding keys
    target_fina_cols = [c for c in fina_cols if c not in ['ts_code', 'ann_date', 'end_date']]
    
    merged = merged.with_columns([
        pl.col(c).cast(pl.Float64, strict=False) for c in target_fina_cols
    ])
    
    # Handle Inf
    # Replace Inf with Null
    # Polars Float64 supports Inf, but we want Null for calculations usually
    merged = merged.with_columns([
        pl.when(pl.col(c).is_infinite()).then(None).otherwise(pl.col(c)).alias(c)
        for c in target_fina_cols
    ])
    
    return merged
