import pyarrow.parquet as pq
import pyarrow as pa
import pandas as pd
from pathlib import Path

fp = r'd:\Trading\data_ever_26_3_14\data\Raw_data\moneyflow_2010_parts\20150708_o00000.parquet'
print(f"Testing {fp}")
try:
    print("Trying pq.read_table...")
    table = pq.read_table(fp)
    print("Success reading table")
    print(table.schema)
except Exception as e:
    print(f"pq.read_table failed: {e}")

try:
    print("\nTrying pd.read_parquet...")
    df = pd.read_parquet(fp)
    print("Success reading with pandas")
    print(df.dtypes)
except Exception as e:
    print(f"pd.read_parquet failed: {e}")
