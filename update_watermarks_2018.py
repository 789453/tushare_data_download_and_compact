import sqlite3
from pathlib import Path

db_path = Path("data/meta/control.sqlite3")
conn = sqlite3.connect(db_path)
datasets = ["index_daily_selected", "cffex_fut_daily_selected", "cffex_opt_daily", "fx_daily_selected"]
for ds in datasets:
    conn.execute("INSERT OR REPLACE INTO dataset_watermark (dataset_name, watermark_value, watermark_col, updated_at) VALUES (?, '20180101', 'trade_date', '2026-04-22T00:00:00Z');", (ds,))
conn.commit()
conn.close()
print("Watermarks updated to 20180101")
