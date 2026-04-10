import os
import time
import pandas as pd
import tushare as ts
from tqdm import tqdm

def get_tushare_pro():
    token = os.environ.get("TUSHARE_TOKEN")
    if not token:
        raise ValueError("Please set TUSHARE_TOKEN environment variable")
    ts.set_token(token)
    return ts.pro_api()

def generate_periods(start_year, end_year):
    periods = []
    for year in range(start_year, end_year + 1):
        for md in ['0331', '0630', '0930', '1231']:
            periods.append(f"{year}{md}")
    return periods

def download_fina_indicator(output_path, start_year=2004, end_year=2026):
    pro = get_tushare_pro()
    periods = generate_periods(start_year, end_year)
    
    all_data = []
    print(f"Downloading fina_indicator_vip data by periods from {start_year} to {end_year}...")
    
    use_vip = True
    for period in tqdm(periods):
        try:
            # 优先尝试 vip 接口按期获取
            df = pro.fina_indicator_vip(period=period)
            if not df.empty:
                all_data.append(df)
            time.sleep(0.12) # 避免触发频率限制
        except Exception as e:
            if "没有权限" in str(e) or "接口权限" in str(e) or "积分" in str(e):
                print(f"\nfina_indicator_vip no permission. {e}")
                use_vip = False
                break
            else:
                print(f"Error fetching period {period}: {e}")
            
    if not use_vip or not all_data:
        print("Falling back to per-stock fetch using fina_indicator.")
        all_data = []
        try:
            daily_basic_path = r"d:\Trading\data_ever_26_3_14\data\Raw_data\daily_basic.parquet"
            daily_df = pd.read_parquet(daily_basic_path, columns=['ts_code'])
            ts_codes = daily_df['ts_code'].unique()
            print(f"Total stocks to fetch: {len(ts_codes)}")
            
            for ts_code in tqdm(ts_codes):
                try:
                    df = pro.fina_indicator(ts_code=ts_code)
                    if not df.empty:
                        all_data.append(df)
                    time.sleep(0.12)
                except Exception as e:
                    print(f"Error fetching stock {ts_code}: {e}")
        except Exception as e2:
            print(f"Fallback failed: {e2}")
            
    if all_data:
        final_df = pd.concat(all_data, ignore_index=True)
        final_df.drop_duplicates(subset=['ts_code', 'ann_date', 'end_date'], keep='last', inplace=True)
        final_df.to_parquet(output_path, index=False)
        print(f"Data saved to {output_path}. Shape: {final_df.shape}")
    else:
        print("No data downloaded.")

if __name__ == "__main__":
    output_file = r"d:\Trading\data_ever_26_3_14\data\Raw_data\fina_indicator.parquet"
    if not os.path.exists(output_file):
        download_fina_indicator(output_file)
    else:
        print(f"File {output_file} already exists, skip downloading.")
