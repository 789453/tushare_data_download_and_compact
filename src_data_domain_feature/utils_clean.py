import numpy as np
import pandas as pd
from typing import Union, Optional, Tuple, Literal
import logging

logger = logging.getLogger(__name__)

def safe_div(numerator: Union[pd.Series, float], denominator: Union[pd.Series, float], 
             epsilon: float = 1e-8, fill_value: float = np.nan, 
             min_abs_den: float = 1e-4) -> pd.Series:
    """
    Safe division with strict denominator checking.
    
    Args:
        numerator: Numerator series or value
        denominator: Denominator series or value
        epsilon: Small value to avoid zero division (used only if strict checking passes but value is 0)
        fill_value: Value to use when denominator is invalid (too small)
        min_abs_den: Minimum absolute value for denominator to be considered valid
    """
    # Ensure inputs are Series for alignment
    if isinstance(numerator, (int, float)):
        numerator = pd.Series(numerator, index=denominator.index if hasattr(denominator, 'index') else None)
    if isinstance(denominator, (int, float)):
        denominator = pd.Series(denominator, index=numerator.index if hasattr(numerator, 'index') else None)
        
    # Check validity
    valid = denominator.notna() & np.isfinite(denominator) & (denominator.abs() >= min_abs_den)
    
    # Initialize result with fill_value
    # Use dtype=float to accommodate NaNs
    result = pd.Series(fill_value, index=numerator.index, dtype=float)
    
    # Perform division only on valid entries
    if valid.any():
        result.loc[valid] = numerator.loc[valid] / denominator.loc[valid]
        
    return result

def fill_missing_grouped(df: pd.DataFrame, group_col: str, target_cols: list, 
                         method: str = 'ffill', limit: Optional[int] = None) -> pd.DataFrame:
    """
    Fill missing values within groups to prevent cross-sectional leakage.
    
    Args:
        df: DataFrame
        group_col: Column to group by (e.g., 'ts_code')
        target_cols: Columns to fill
        method: 'ffill' or 'bfill'
        limit: Max number of consecutive NaNs to fill
    """
    if method not in ['ffill', 'bfill']:
        raise ValueError("Method must be 'ffill' or 'bfill'")
    
    # Using groupby transform is safer than sorting and filling globally
    # Note: caller must ensure df is sorted by time if method is time-sensitive
    
    for col in target_cols:
        if method == 'ffill':
            df[col] = df.groupby(group_col)[col].ffill(limit=limit)
        else:
            df[col] = df.groupby(group_col)[col].bfill(limit=limit)
            
    return df

def clip_outliers(series: pd.Series, lower_quantile: float = 0.01, upper_quantile: float = 0.99) -> pd.Series:
    """
    Clip outliers based on quantiles. Deprecated: use winsorize_series.
    """
    return winsorize_series(series, limits=(lower_quantile, 1-upper_quantile), strategy='quantile')

def clip_by_bounds(series: pd.Series, lower: Optional[float] = None, upper: Optional[float] = None) -> pd.Series:
    """
    Clip values by hard bounds.
    """
    return series.clip(lower=lower, upper=upper)

def winsorize_series(series: pd.Series, limits: tuple = (0.01, 0.01), 
                     strategy: Literal['quantile', 'sigma', 'mad', 'none'] = 'quantile') -> pd.Series:
    """
    Winsorize a series (clip at quantiles or sigma).
    
    Args:
        series: Input series
        limits: 
            - For 'quantile': (lower_percentile, upper_percentile), e.g., (0.01, 0.01) clips at 1% and 99%.
            - For 'sigma': (n_sigma, ignored), e.g., (3.0, 0) clips at mean +/- 3std.
            - For 'mad': (n_mad, ignored), e.g., (5.0, 0) clips at median +/- 5mad.
        strategy: 'quantile', 'sigma', 'mad', or 'none'.
    """
    if series.empty or strategy == 'none':
        return series
        
    # Skip NaNs for calculation
    valid_data = series.dropna()
    if valid_data.empty:
        return series

    if strategy == 'quantile':
        lower_q = valid_data.quantile(limits[0])
        upper_q = valid_data.quantile(1 - limits[1])
        return series.clip(lower=lower_q, upper=upper_q)
    
    elif strategy == 'sigma':
        mean = valid_data.mean()
        std = valid_data.std()
        limit = limits[0]
        return series.clip(lower=mean - limit * std, upper=mean + limit * std)
        
    elif strategy == 'mad':
        median = valid_data.median()
        mad = (valid_data - median).abs().median()
        limit = limits[0]
        # Robust sigma estimate = 1.4826 * MAD
        # Often we just use n * MAD directly or n * robust_sigma
        # Here we use n * MAD for simplicity, or we can align with sigma
        return series.clip(lower=median - limit * mad, upper=median + limit * mad)
        
    return series

def standardize_date(series: pd.Series) -> pd.Series:
    """
    Standardize date format to string YYYYMMDD.
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        return series.dt.strftime('%Y%m%d')
    return series.astype(str)

def check_ohlc_validity(df: pd.DataFrame, price_floor: float = 0.01) -> pd.Series:
    """
    Return a boolean mask where OHLC data is valid.
    Rules:
    1. All > price_floor
    2. high >= max(open, close)
    3. low <= min(open, close)
    4. high >= low
    """
    # Basic existence and positive
    c1 = (df['open'] > price_floor) & (df['high'] > price_floor) & \
         (df['low'] > price_floor) & (df['close'] > price_floor)
    
    # Geometry
    # Allow small epsilon for floating point errors
    c2 = df['high'] >= df[['open', 'close']].max(axis=1) - 1e-4
    c3 = df['low'] <= df[['open', 'close']].min(axis=1) + 1e-4
    c4 = df['high'] >= df['low']
    
    return c1 & c2 & c3 & c4
