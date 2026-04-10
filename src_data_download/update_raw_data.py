from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ts_download_utils import (
    ensure_dir,
    get_parquet_max_date,
    today_yyyymmdd,
)
# Import our run functions from the scripts
import download_trade_date_generic
import download_cyq_perf_2026
import download_stk_mins_2026
import compact_raw_data

def update_dataset(name: str, raw_dir: Path, start_date: str, end_date: str, max_workers: int):
    print(f"\n>>> 更新数据集: {name} ({start_date} -> {end_date})")
    
    if name in ["daily", "daily_basic", "moneyflow", "stk_limit", "suspend_d"]:
        return download_trade_date_generic.run(
            api_name=name,
            raw_dir=raw_dir,
            start_date=start_date,
            end_date=end_date,
            max_workers=max_workers,
            overwrite=False
        )
    elif name == "cyq_perf":
        stock_basic = raw_dir / "stock_basic.parquet"
        return download_cyq_perf_2026.run(
            raw_dir=raw_dir,
            stock_basic=stock_basic,
            start_date=start_date,
            end_date=end_date,
            max_workers=2, # Keep it low for cyq_perf
            overwrite=False
        )
    elif name.startswith("stk_mins"):
        freq = name.split("_")[-1] if "_" in name else "60min"
        stock_basic = raw_dir / "stock_basic.parquet"
        return download_stk_mins_2026.run(
            raw_dir=raw_dir,
            stock_basic=stock_basic,
            start_date=start_date,
            end_date=end_date,
            freq=freq,
            max_workers=max_workers,
            overwrite=False
        )
    return {"dataset": name, "status": "unknown"}

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--raw-dir", default=r"d:\Trading\data_ever_26_3_14\data\Raw_data")
    p.add_argument("--start-date", default=None, help="默认会自动寻找已有文件的最大日期")
    p.add_argument("--end-date", default=today_yyyymmdd())
    p.add_argument("--max-workers", type=int, default=4)
    p.add_argument("--datasets", default="daily,daily_basic,moneyflow,stk_limit,suspend_d,cyq_perf,stk_mins_60min")
    args = p.parse_args()

    raw_dir = Path(args.raw_dir)
    ensure_dir(raw_dir)
    end_date = str(args.end_date)
    datasets = [x.strip() for x in str(args.datasets).split(",") if x.strip()]

    reports = []
    for name in datasets:
        # Determine start date
        start = args.start_date
        if not start:
            # Try to find max date in existing full file
            main_file = raw_dir / f"{name}.parquet"
            print(f"DEBUG: 正在检查历史文件: {main_file}")
            
            # stk_mins 使用 trade_time 而非 trade_date
            date_col = "trade_time" if name.startswith("stk_mins") else "trade_date"
            max_d = get_parquet_max_date(main_file, date_col=date_col)
            
            # 如果是 trade_time，取前 8 位日期
            if max_d and len(max_d) > 8:
                max_d = max_d[:8]
            
            print(f"DEBUG: 获取到的最大日期: {max_d}")
     
            if max_d:
                # 情况 A: 找到已有文件，从最大日期的次日继续 (断点续传)
                # 注意：这里通常需要 +1 天，具体取决于你的 update_dataset 逻辑是否包含 start 当天
                start = max_d 
                print(f"✅ 发现历史数据 {name}，将从 {start} 续传...")
            else:
                # 情况 B: 未找到已有文件，且用户未指定 start
                # 【策略变更】不再默认从 1990 年开始，而是直接抛出异常退出
                error_msg = (
                    f"❌ 错误: 未找到 {name} 的历史文件 ({main_file.name})，且未指定 --start 日期。\n"
                    f"   为防止意外触发全量历史下载 (1990-至今)，程序已终止。\n"
                    f"   解决方法:\n"
                    f"   1. 显式指定起始日期: python script.py --name {name} --start 20200101\n"
                    f"   2. 或者先手动放置一个初始文件到 {raw_dir}"
                )
                print(error_msg)
                sys.exit(1)  # 直接退出程序，返回错误码 1
        
        res = update_dataset(name, raw_dir, start, end_date, args.max_workers)
        reports.append(res)
        
        # After each dataset, try to compact if there are parts
        print(f"--- 合并 {name} ---")
        compact_res = compact_raw_data.compact_generic(raw_dir, name)
        print(compact_res)

    print("\n" + "="*50)
    print("一键更新完成报告")
    print("="*50)
    for r in reports:
        print(r)
        
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
