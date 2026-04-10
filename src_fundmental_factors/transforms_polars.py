import polars as pl
import numpy as np

def winsorize(col: str, limits: tuple = (0.02, 0.02)) -> pl.Expr:
    """Winsorize a column."""
    expr = pl.col(col)
    lower = expr.quantile(limits[0])
    upper = expr.quantile(1 - limits[1])
    return expr.clip(lower, upper)

def standardize(col: str) -> pl.Expr:
    """Z-score standardization."""
    expr = pl.col(col)
    mean = expr.mean()
    std = expr.std()
    return (expr - mean) / std.fill_null(1.0)  # Avoid division by zero

def cs_rank(col: str) -> pl.Expr:
    """Cross-sectional rank (percentile)."""
    return pl.col(col).rank("ordinal") / pl.col(col).count()

def ind_rank(col: str, ind_col: str = 'l2_name', min_n: int = 5) -> pl.Expr:
    """
    Industry cross-sectional rank.
    This logic needs to be applied within a context (e.g. over(trade_date, ind_col)).
    But `over` doesn't support filter inside easily for min_n check.
    Usually applied as: df.with_columns(ind_rank('pe', 'l1').over('trade_date', 'l1'))
    Here we return the expression.
    To handle min_n, we might need a when-then.
    """
    count = pl.col(col).count().over(ind_col)
    rank = pl.col(col).rank("ordinal").over(ind_col) / count
    return pl.when(count >= min_n).then(rank).otherwise(None)

def ts_lag(col: str, k: int = 1) -> pl.Expr:
    """Time-series lag. Assumes data is sorted by date within group."""
    return pl.col(col).shift(k)

def ts_roc(col: str, k: int = 1) -> pl.Expr:
    """Time-series rate of change."""
    prev = pl.col(col).shift(k)
    return pl.col(col) / prev - 1.0

def ts_diff(col: str, k: int = 1) -> pl.Expr:
    """Time-series difference."""
    return pl.col(col) - pl.col(col).shift(k)

def ts_zscore(col: str, k: int = 20) -> pl.Expr:
    """Rolling z-score."""
    return (pl.col(col) - pl.col(col).rolling_mean(k)) / pl.col(col).rolling_std(k)

def neutralize_numpy(df: pl.DataFrame, col: str, ind_col: str, size_col: str) -> pl.Series:
    """
    Neutralize a column against industry and size using numpy (for map_batches).
    Input df must have columns: [col, ind_col, size_col]
    """
    # This function runs on a single group (e.g. one day)
    y = df[col].to_numpy()
    valid_mask = ~np.isnan(y)
    
    # Check size
    if size_col in df.columns:
        s = df[size_col].to_numpy()
        valid_mask &= ~np.isnan(s)
    else:
        s = None
        
    # Check industry
    if ind_col in df.columns:
        ind = df[ind_col].to_numpy()
        # Polars string columns to numpy are object, might contain None
        # But we assume preprocess handled NAs or we check here
        # If ind is None, valid_mask will be false if we rely on it
        pass
    else:
        ind = None

    if np.sum(valid_mask) < 30:
        return pl.Series(values=[None]*len(df), dtype=pl.Float64)

    y_valid = y[valid_mask]
    
    # Winsorize Y (simple percentile clip on valid data)
    lower = np.nanpercentile(y_valid, 2)
    upper = np.nanpercentile(y_valid, 98)
    y_valid = np.clip(y_valid, lower, upper)
    
    # Build X
    n = len(y_valid)
    X_list = [np.ones((n, 1))]
    
    if s is not None:
        s_v = s[valid_mask]
        # Log, winsorize, standardize
        s_v = np.log(s_v)
        # winsorize size
        s_lower = np.nanpercentile(s_v, 2)
        s_upper = np.nanpercentile(s_v, 98)
        s_v = np.clip(s_v, s_lower, s_upper)
        # standardize
        s_mean = np.nanmean(s_v)
        s_std = np.nanstd(s_v)
        if s_std > 0:
            s_v = (s_v - s_mean) / s_std
        else:
            s_v = s_v - s_mean
        X_list.append(s_v.reshape(-1, 1))
        
    if ind is not None:
        ind_v = ind[valid_mask]
        # One-hot encoding
        # Get unique categories
        uniques, inverse = np.unique(ind_v, return_inverse=True)
        # Create dummies (drop first to avoid multicollinearity with intercept? 
        # Actually standard OLS with intercept usually drops one.
        # Let's drop the first category.
        if len(uniques) > 1:
            dummies = np.eye(len(uniques))[inverse]
            # Drop first column
            dummies = dummies[:, 1:]
            X_list.append(dummies)
            
    X = np.hstack(X_list)
    
    # Solve
    try:
        # beta = (X'X)^-1 X'y
        # Use lstsq
        beta, _, _, _ = np.linalg.lstsq(X, y_valid, rcond=None)
        resid_valid = y_valid - X @ beta
        
        # Fill result
        res = np.full(len(df), np.nan)
        res[valid_mask] = resid_valid
        return pl.Series(values=res, dtype=pl.Float64)
    except:
        return pl.Series(values=[None]*len(df), dtype=pl.Float64)

def neutralize_expr(col: str, ind_col: str = 'l1_name', size_col: str = 'circ_mv') -> pl.Expr:
    """
    Returns an expression that applies neutralization group-wise.
    Note: map_groups/apply is not lazy-compatible in standard streaming.
    It returns a Struct with the result, or we can use it in a select/with_columns context grouped by trade_date.
    
    Usage:
    df.group_by('trade_date').map_groups(
        lambda df: df.with_columns(res = neutralize_numpy(df, ...))
    )
    
    But to make it compatible with lazy execution plan as much as possible, 
    we might need to define a custom function or use map_batches on the group.
    
    However, strictly speaking, `neutralize` is a cross-sectional operator.
    We will implement the orchestration in the main loop or factor calculation function 
    to apply this per date (or group_by('trade_date').apply(...)).
    """
    pass 
