import pandas as pd
import os

class DataLoader:
    def __init__(self, data_dir=r"d:\Trading\data_ever_26_3_14\data\Raw_data"):
        self.data_dir = data_dir
        
    def load_daily_basic(self):
        path = os.path.join(self.data_dir, "daily_basic.parquet")
        df = pd.read_parquet(path)
        # Ensure trade_date is string
        df['trade_date'] = df['trade_date'].astype(str)
        return df
        
    def load_fina_indicator(self):
        path = os.path.join(self.data_dir, "fina_indicator.parquet")
        if not os.path.exists(path):
            raise FileNotFoundError(f"{path} not found. Please run tushare_downloader.py first.")
        df = pd.read_parquet(path)
        # Ensure dates are strings
        df['ann_date'] = df['ann_date'].astype(str)
        df['end_date'] = df['end_date'].astype(str)
        return df
        
    def load_industry(self):
        path = os.path.join(self.data_dir, "index_member_all.parquet")
        df = pd.read_parquet(path)
        df['in_date'] = df['in_date'].astype(str)
        df['out_date'] = df['out_date'].fillna('20991231').astype(str) # Fill na with future date
        return df
