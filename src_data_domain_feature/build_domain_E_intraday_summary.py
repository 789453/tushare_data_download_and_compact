import polars as pl
import numpy as np
import pandas as pd
from config import (
    RAW_STK_MINS,
    DOMAIN_DATA_DIR,
    FACTOR_READY_DIR,
    EPSILON
)
from utils_io import save_parquet
from utils_clean import winsorize_series
import logging

logger = logging.getLogger(__name__)

def build_domain_E():
    logger.info("Building Domain E: Intraday Summary (1h) with Polars...")
    
    q = pl.scan_parquet(RAW_STK_MINS)
    
    df = (
        q
        .unique(subset=["ts_code", "trade_time"], keep="last")
        .with_columns([
            pl.col("trade_time").str.to_datetime(),
            pl.col("vol").abs(),
            pl.col("amount").abs(),
        ])
        .with_columns([
            pl.col("trade_time").dt.strftime("%Y%m%d").alias("trade_date"),
            pl.col("trade_time").dt.hour().alias("hour"),
            pl.col("trade_time").dt.minute().alias("minute"),
        ])
        .sort(["ts_code", "trade_time"])
    ).collect()
    
    logger.info(f"Loaded and preprocessed {df.height} rows.")
    
    price_floor = 0.05
    
    df = df.with_columns([
        pl.when(pl.col("open").abs() >= price_floor)
        .then(pl.col("close") / pl.col("open") - 1)
        .otherwise(None)
        .alias("ret_h")
    ])
    
    df = df.with_columns([
        pl.col("ret_h").abs().alias("abs_ret_h")
    ])
    
    logger.info("Aggregating to daily level...")
    
    # We define first hour as time <= 10:30 (hour <= 10)
    # Last hour as time >= 14:00 and <= 15:00 (we can just use hour == 15 for 14:00-15:00 bar)
    agg_exprs = [
        # Daily OHLC
        pl.col("open").first().alias("open_day"),
        pl.col("close").last().alias("close_day"),
        pl.col("high").max().alias("high_day"),
        pl.col("low").min().alias("low_day"),
        
        # Volume/Amount
        pl.col("vol").sum().alias("vol_total"),
        pl.col("amount").sum().alias("amount_total"),
        
        # Returns
        pl.col("abs_ret_h").sum().alias("sum_abs_ret"),
        pl.col("ret_h").std().alias("hourly_volatility"),
        
        # First Hour Specifics
        pl.col("open").filter(pl.col("hour") <= 10).first().alias("hour1_open"),
        pl.col("close").filter(pl.col("hour") <= 10).last().alias("hour1_close"),
        pl.col("vol").filter(pl.col("hour") <= 10).sum().alias("hour1_vol"),
        pl.col("hour").filter(pl.col("hour") <= 10).len().alias("hour1_bar_count"),
        
        # Last Hour Specifics
        pl.col("open").filter(pl.col("hour") == 15).first().alias("lasthour_open"),
        pl.col("close").filter(pl.col("hour") == 15).last().alias("lasthour_close"),
        
        # Afternoon Volume (hour >= 13)
        pl.col("vol").filter(pl.col("hour") >= 13).sum().fill_null(0).alias("vol_pm"),
        
        # High/Low Time Indices
        pl.col("high").arg_max().alias("high_time_idx"),
        pl.col("low").arg_min().alias("low_time_idx"),
        
        pl.len().alias("count")
    ]
    
    df_daily = (
        df
        .sort(["ts_code", "trade_time"])
        .group_by(["ts_code", "trade_date"], maintain_order=True)
        .agg(agg_exprs)
    )
    
    logger.info("Calculating derived features...")
    
    def pl_safe_div(num, den, min_abs_den=1e-4):
        return (
            pl.when(den.abs() >= min_abs_den)
            .then(num / den)
            .otherwise(None)
        )
    
    # 1. Base Validations & Flags
    df_daily = df_daily.with_columns([
        ((pl.col("open_day") <= 0) | (pl.col("close_day") <= 0) | 
         (pl.col("high_day") <= 0) | (pl.col("low_day") <= 0)).cast(pl.Int8).alias("day_price_nonpositive_flag"),
        
        ((pl.col("vol_total") == 0) & (pl.col("count") >= 1)).cast(pl.Int8).alias("no_trade_day_flag"),
        (pl.col("count") == 0).cast(pl.Int8).alias("missing_intraday_source_flag"),
        
        ((pl.col("count") >= 2) & (pl.col("sum_abs_ret") == 0)).cast(pl.Int8).alias("sum_abs_ret_zero_flag"),
        
        (pl.col("count") < 2).cast(pl.Int8).alias("low_bar_count_flag")
    ])
    
    # Filter out records where core prices are invalid or bar count < 2 for intraday derivations
    valid_mask = (pl.col("day_price_nonpositive_flag") == 0) & (pl.col("count") >= 2)
    
    # 2. First Hour Returns
    hour1_has_trade = (pl.col("hour1_vol") > 0)
    hour1_valid = valid_mask & hour1_has_trade & (pl.col("hour1_open") > price_floor) & (pl.col("hour1_close") > price_floor)
    
    df_daily = df_daily.with_columns([
        pl.when(hour1_valid)
        .then(pl.col("hour1_close") / pl.col("hour1_open") - 1)
        .otherwise(None)
        .alias("hour1_ret"),
        
        (~hour1_has_trade).cast(pl.Int8).alias("hour1_has_trade_zero_flag"),
        (pl.col("hour1_bar_count") == 1).cast(pl.Int8).alias("hour1_single_trade_flag")
    ])
    
    # 3. Last Hour Returns
    lasthour_valid = valid_mask & (pl.col("lasthour_open") > price_floor) & (pl.col("lasthour_close") > price_floor)
    df_daily = df_daily.with_columns([
        pl.when(lasthour_valid)
        .then(pl.col("lasthour_close") / pl.col("lasthour_open") - 1)
        .otherwise(None)
        .alias("lasthour_ret")
    ])
    
    # 4. Midday Reversal
    df_daily = df_daily.with_columns([
        (pl.col("lasthour_ret") - pl.col("hour1_ret")).alias("midday_reversal")
    ])
    
    # 5. Intraday Trend Eff
    # Formula: (close_day - open_day) / sum_abs_ret
    # Extreme values occur when sum_abs_ret is very small.
    # We should add a flag for small denominator and maybe mask very extreme values in robust version.
    day_move = pl.col("close_day") - pl.col("open_day")
    
    # New flag: small denominator for trend efficiency
    # If sum_abs_ret < 1e-4 (basically zero volatility), the ratio explodes.
    df_daily = df_daily.with_columns([
        (pl.col("sum_abs_ret") < 1e-3).cast(pl.Int8).alias("intraday_trend_eff_den_small_flag")
    ])
    
    # Raw calculation (keep extreme values)
    df_daily = df_daily.with_columns([
        pl.when(valid_mask)
        .then(pl_safe_div(day_move, pl.col("sum_abs_ret"), min_abs_den=1e-5))
        .otherwise(None)
        .alias("intraday_trend_eff")
    ])
    
    # 6. Volume Concentration PM
    df_daily = df_daily.with_columns([
        pl.when(valid_mask)
        .then(pl_safe_div(pl.col("vol_pm"), pl.col("vol_total"), min_abs_den=1.0).clip(0.0, 1.0))
        .otherwise(None)
        .alias("volume_concentration_pm")
    ])
    
    # 7. VWAP Bias 1H
    # Correct VWAP formula: VWAP = amount / vol. Removing the rogue *10.
    vwap_day = pl_safe_div(pl.col("amount_total"), pl.col("vol_total"), min_abs_den=1.0)
    anchor_vwap = pl.max_horizontal([vwap_day, pl.col("close_day")]).clip(lower_bound=price_floor)
    
    df_daily = df_daily.with_columns([
        pl.when(valid_mask)
        .then(pl_safe_div(pl.col("close_day") - vwap_day, anchor_vwap, min_abs_den=price_floor))
        .otherwise(None)
        .alias("vwap_close_bias_1h")
    ])
    
    # 8. High Low Time Skew
    count_den = pl.col("count") - 1
    df_daily = df_daily.with_columns([
        pl.when(valid_mask)
        .then(pl_safe_div(
            pl.col("high_time_idx").cast(pl.Float64) - pl.col("low_time_idx").cast(pl.Float64),
            count_den.cast(pl.Float64),
            min_abs_den=1.0
        ).clip(-1.0, 1.0))
        .otherwise(None)
        .alias("high_low_time_skew")
    ])
    
    # Set invalid hourly_volatility to None
    df_daily = df_daily.with_columns([
        pl.when(~valid_mask)
        .then(None)
        .otherwise(pl.col("hourly_volatility"))
        .alias("hourly_volatility")
    ])
    
    logger.info("Converting to Pandas for final cleaning and saving...")
    df_pd = df_daily.to_pandas()
    
    # Cleaning / Winsorizing (Only for robust version, keeping raw)
    # For trend efficiency, we might want to mask really crazy values even in robust, or rely on winsorize.
    # 5-sigma is good.
    df_pd['intraday_trend_eff_robust'] = winsorize_series(df_pd['intraday_trend_eff'], limits=(5.0, 0.0), strategy='sigma')
    
    # 5. Save Domain Table
    domain_path = DOMAIN_DATA_DIR / "domain_intraday_1h_summary.parquet"
    save_parquet(df_pd, domain_path)
    
    # 6. Save Feature Table
    feature_cols = [
        'ts_code', 'trade_date',
        'hour1_ret', 'lasthour_ret', 'midday_reversal',
        'intraday_trend_eff', 'intraday_trend_eff_robust', 'hourly_volatility',
        'volume_concentration_pm', 'vwap_close_bias_1h',
        'high_low_time_skew',
        'day_price_nonpositive_flag', 'no_trade_day_flag', 'missing_intraday_source_flag',
        'sum_abs_ret_zero_flag', 'low_bar_count_flag', 'hour1_has_trade_zero_flag', 'hour1_single_trade_flag',
        'intraday_trend_eff_den_small_flag'
    ]
    feature_path = FACTOR_READY_DIR / "feature_E_intraday_summary.parquet"
    save_parquet(df_pd[feature_cols], feature_path)
    
    logger.info("Domain E processing complete.")

if __name__ == "__main__":
    build_domain_E()
