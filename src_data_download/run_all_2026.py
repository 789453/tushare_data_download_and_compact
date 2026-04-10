from __future__ import annotations

import argparse
from pathlib import Path

from compact_2026 import compact_cyq_perf, compact_stk_mins, compact_trade_date_dataset
from compare_old_2026 import run as run_compare_old
from download_cyq_perf_2026 import run as run_cyq_perf
from download_daily_2026 import run as run_daily
from download_daily_basic_2026 import run as run_daily_basic
from download_moneyflow_2026 import run as run_moneyflow
from download_stk_mins_2026 import run as run_stk_mins
from ts_download_utils import ensure_dir, today_yyyymmdd
from verify_2026 import run as run_verify


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--raw-dir", default=r"d:\Trading\data_ever_26_3_14\data\Raw_data")
    p.add_argument("--stock-basic", default=r"d:\Trading\data_ever_26_3_14\data\Raw_data\stock_basic.parquet")
    p.add_argument("--start-date", default="20260101")
    p.add_argument("--end-date", default=today_yyyymmdd())
    p.add_argument("--datasets", default="moneyflow,daily_basic,daily,cyq_perf,stk_mins")
    p.add_argument("--max-workers", type=int, default=4)
    p.add_argument("--cyq-workers", type=int, default=2)
    p.add_argument("--mins-workers", type=int, default=4)
    p.add_argument("--cyq-shard-idx", type=int, default=0)
    p.add_argument("--cyq-shard-count", type=int, default=1)
    p.add_argument("--mins-shard-idx", type=int, default=0)
    p.add_argument("--mins-shard-count", type=int, default=1)
    p.add_argument("--stk-mins-freq", default="60min")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--compact", action="store_true")
    p.add_argument("--verify", action="store_true")
    p.add_argument("--compare-old", action="store_true")
    p.add_argument("--old-path", default=r"d:\Trading\data_ever_26_3_14\data\Raw_data\dataset_2026_old.parquet")
    args = p.parse_args()

    raw_dir = Path(args.raw_dir)
    ensure_dir(raw_dir)

    datasets = set(x.strip() for x in str(args.datasets).split(",") if x.strip())
    start_date = str(args.start_date)
    end_date = str(args.end_date)
    year = start_date[:4]
    freq = str(args.stk_mins_freq)

    reports: list[dict] = []

    if "moneyflow" in datasets:
        reports.append(
            run_moneyflow(
                raw_dir=raw_dir,
                start_date=start_date,
                end_date=end_date,
                max_workers=int(args.max_workers),
                overwrite=bool(args.overwrite),
            )
        )
    if "daily_basic" in datasets:
        reports.append(
            run_daily_basic(
                raw_dir=raw_dir,
                start_date=start_date,
                end_date=end_date,
                max_workers=int(args.max_workers),
                overwrite=bool(args.overwrite),
            )
        )
    if "daily" in datasets:
        reports.append(
            run_daily(
                raw_dir=raw_dir,
                start_date=start_date,
                end_date=end_date,
                max_workers=int(args.max_workers),
                overwrite=bool(args.overwrite),
            )
        )
    if "cyq_perf" in datasets:
        reports.append(
            run_cyq_perf(
                raw_dir=raw_dir,
                stock_basic=Path(args.stock_basic),
                start_date=start_date,
                end_date=end_date,
                max_workers=int(args.cyq_workers),
                overwrite=bool(args.overwrite),
                shard_idx=int(args.cyq_shard_idx),
                shard_count=int(args.cyq_shard_count),
            )
        )
    if "stk_mins" in datasets:
        reports.append(
            run_stk_mins(
                raw_dir=raw_dir,
                stock_basic=Path(args.stock_basic),
                start_date=start_date,
                end_date=end_date,
                freq=freq,
                max_workers=int(args.mins_workers),
                overwrite=bool(args.overwrite),
                shard_idx=int(args.mins_shard_idx),
                shard_count=int(args.mins_shard_count),
            )
        )

    if args.compact:
        if "moneyflow" in datasets:
            reports.append(compact_trade_date_dataset(raw_dir, "moneyflow", year, start_date=start_date, end_date=end_date))
        if "daily_basic" in datasets:
            reports.append(compact_trade_date_dataset(raw_dir, "daily_basic", year, start_date=start_date, end_date=end_date))
        if "daily" in datasets:
            reports.append(compact_trade_date_dataset(raw_dir, "daily", year, start_date=start_date, end_date=end_date))
        if "cyq_perf" in datasets:
            reports.append(compact_cyq_perf(raw_dir, year, start_date=start_date, end_date=end_date))
        if "stk_mins" in datasets:
            reports.append(compact_stk_mins(raw_dir, year, freq, start_date=start_date, end_date=end_date))

    if args.verify:
        reports.extend(
            run_verify(
                raw_dir=str(raw_dir),
                start_date=start_date,
                end_date=end_date,
                stk_mins_freq=freq,
            )
        )

    if args.compare_old:
        reports.extend(run_compare_old(raw_dir=str(raw_dir), old_path=str(args.old_path), year=year))

    for r in reports:
        print(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
