import pandas as pd
import numpy as np
from joblib import Parallel, delayed

def winsorize_series(s, limits=(0.02, 0.02)):
    """Winsorize a pandas Series or numpy array."""
    if isinstance(s, pd.Series):
        return s.clip(lower=s.quantile(limits[0]), upper=s.quantile(1 - limits[1]))
    else:
        # Numpy version
        s = np.array(s)
        lower = np.nanpercentile(s, limits[0] * 100)
        upper = np.nanpercentile(s, (1 - limits[1]) * 100)
        return np.clip(s, lower, upper)

def standardize_series(s):
    """Z-score standardization."""
    if isinstance(s, pd.Series):
        std = s.std()
        if pd.isna(std) or std == 0:
            return s - s.mean()
        return (s - s.mean()) / std
    else:
        s = np.array(s)
        std = np.nanstd(s)
        if std == 0 or np.isnan(std):
            return s - np.nanmean(s)
        return (s - np.nanmean(s)) / std

def cs_rank(df, col):
    """Cross-sectional rank (0 to 1) for a column per trade_date."""
    # Groupby rank is already reasonably optimized in pandas
    return df.groupby('trade_date')[col].rank(pct=True)

def ind_rank(df, col, ind_col='l2_name', min_n=5):
    """Industry cross-sectional rank."""
    # Optimized: If ind_col is categorical, this can be faster, but let's stick to simple groupby
    # Parallelizing this is usually overkill due to overhead, unless groups are huge.
    def _rank(group):
        if len(group) < min_n:
            return pd.Series(np.nan, index=group.index)
        return group.rank(pct=True)
    return df.groupby(['trade_date', ind_col])[col].transform(_rank)

def _regress_one_day(df_day, col, ind_col, size_col):
    """Helper function for parallel neutralization."""
    y = df_day[col].values
    
    # 1. Identify valid mask
    valid_mask = ~pd.isna(y)
    
    if size_col in df_day.columns:
        size_vals = df_day[size_col].values
        valid_mask &= ~pd.isna(size_vals)
    else:
        size_vals = None
        
    if ind_col in df_day.columns:
        ind_vals = df_day[ind_col].values
        valid_mask &= ~pd.isna(ind_vals)
    else:
        ind_vals = None
        
    if np.sum(valid_mask) < 30:
        return pd.Series(np.nan, index=df_day.index)
        
    # 2. Prepare Y and X for valid rows
    y_valid = y[valid_mask]
    y_valid = winsorize_series(y_valid) # Winsorize Y before regression
    
    # Construct X matrix
    # Intercept
    n_valid = len(y_valid)
    X_list = [np.ones((n_valid, 1))]
    
    # Size factor
    if size_vals is not None:
        s_v = size_vals[valid_mask].astype(float)
        # Log size, winsorize, standardize
        s_v = np.log(s_v)
        s_v = winsorize_series(s_v)
        s_v = standardize_series(s_v)
        X_list.append(s_v.reshape(-1, 1))
        
    # Industry dummies
    if ind_vals is not None:
        # Use pandas get_dummies for simplicity and speed on small arrays
        # drop_first=True to avoid collinearity with intercept? 
        # Actually with OLS intercept, we usually drop one category or use constrained regression.
        # Standard way: drop_first=True
        ind_v = ind_vals[valid_mask]
        dummies = pd.get_dummies(ind_v, drop_first=True, dtype=float).values
        if dummies.shape[1] > 0:
            X_list.append(dummies)
            
    X = np.hstack(X_list)
    
    # 3. Solve OLS: (X'X)^-1 X'Y
    # Or use lstsq which is more robust
    try:
        # residuals = y - X @ beta
        # beta = np.linalg.lstsq(X, y_valid, rcond=None)[0]
        # Faster approach if X is well behaved: solve normal equations
        # But lstsq is safer for singular matrices (e.g. dummy trap)
        beta, _, _, _ = np.linalg.lstsq(X, y_valid, rcond=None)
        resid_valid = y_valid - X @ beta
        
        # 4. Fill result
        res = np.full(len(df_day), np.nan)
        res[valid_mask] = resid_valid
        return pd.Series(res, index=df_day.index)
        
    except Exception:
        return pd.Series(np.nan, index=df_day.index)

def neutralize(df, col, ind_col='l1_name', size_col='circ_mv', n_jobs=-1):
    """
    Neutralize a column against industry and size per trade_date.
    Uses Parallel execution for speedup.
    """
    print(f"Neutralizing {col} with n_jobs={n_jobs}...")
    
    # Group by date
    groups = list(df.groupby('trade_date'))
    
    # Run in parallel
    results = Parallel(n_jobs=n_jobs)(
        delayed(_regress_one_day)(group, col, ind_col, size_col) 
        for date, group in groups
    )
    
    # Combine results
    return pd.concat(results).sort_index()

def ts_lag(df, col, k=1):
    """Time-series lag per ts_code. Assumes df is sorted by ts_code, trade_date."""
    # Optimization: If sorted, we can just shift, but we must respect ts_code boundaries.
    # df.groupby('ts_code')[col].shift(k) is safe but slow-ish.
    # Faster: use mask.
    return df.groupby('ts_code')[col].shift(k)

def ts_roc(df, col, k=1):
    """Time-series rate of change."""
    prev = ts_lag(df, col, k)
    return df[col] / prev - 1.0

def ts_diff(df, col, k=1):
    """Time-series difference."""
    return df[col] - ts_lag(df, col, k)

def ts_zscore(df, col, k=20):
    """Rolling z-score."""
    # This is hard to vectorize perfectly without groupby, but groupby().rolling() is standard.
    # To optimize: if data is strictly sorted, we could use stride_tricks or numba, 
    # but for now standard pandas is robust enough.
    roll = df.groupby('ts_code')[col].rolling(window=k, min_periods=k//2)
    
    # The result of roll.mean() has a MultiIndex (ts_code, index).
    # We need to align it back to df.
    # Dropping level 0 (ts_code) assumes the order is preserved and matches df.
    # It is safer to re-index.
    
    mean = roll.mean().reset_index(level=0, drop=True)
    std = roll.std().reset_index(level=0, drop=True)
    
    # Make sure index alignment is correct
    return (df[col] - mean) / std

def bucket(df, col, q=5):
    """Cross-sectional bucket (1 to q) per trade_date."""
    return df.groupby('trade_date')[col].transform(lambda x: pd.qcut(x, q, labels=False, duplicates='drop') + 1)
