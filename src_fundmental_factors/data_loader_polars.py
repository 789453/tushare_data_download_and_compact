import polars as pl
import os

class DataLoaderPolars:
    def __init__(self, data_dir=r"d:\Trading\data_ever_26_3_14\data\Raw_data"):
        self.data_dir = data_dir
        
    def load_daily_basic(self) -> pl.LazyFrame:
        """Load daily basic data."""
        path = os.path.join(self.data_dir, "daily_basic.parquet")
        lf = pl.scan_parquet(path)
        # Ensure trade_date is string for consistency, or convert to Date?
        # Polars join_asof prefers integers or datetime.
        # Let's use str for now, then convert to Date in preprocess.
        return lf
        
    def load_industry(self) -> pl.LazyFrame:
        """Load industry classification."""
        path = os.path.join(self.data_dir, "index_member_all.parquet")
        lf = pl.scan_parquet(path)
        
        # Ensure dates are strings or handled
        # Handle out_date nulls with '20991231'
        return lf.with_columns(
            pl.col('out_date').fill_null('20991231')
        )
        
    def load_fina_indicator(self) -> pl.LazyFrame:
        """Load quarterly financial indicators."""
        path = os.path.join(self.data_dir, "fina_indicator.parquet")
        if not os.path.exists(path):
            raise FileNotFoundError(f"{path} not found.")
        lf = pl.scan_parquet(path)
        return lf
