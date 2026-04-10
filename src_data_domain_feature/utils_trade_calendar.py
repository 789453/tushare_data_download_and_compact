import pandas as pd
from .utils_io import load_parquet
from .config import RAW_DAILY

def get_trade_calendar() -> pd.DataFrame:
    """
    Get unique trade dates from daily.parquet.
    Returns a DataFrame with 'trade_date' column.
    """
    # Only read trade_date column to be fast
    df = load_parquet(RAW_DAILY, columns=['trade_date'])
    dates = df['trade_date'].drop_duplicates().sort_values().reset_index(drop=True)
    return pd.DataFrame({'trade_date': dates})

def filter_by_calendar(df: pd.DataFrame, calendar_df: pd.DataFrame) -> pd.DataFrame:
    """
    Filter dataframe to only include dates present in the calendar.
    """
    return df[df['trade_date'].isin(calendar_df['trade_date'])]
