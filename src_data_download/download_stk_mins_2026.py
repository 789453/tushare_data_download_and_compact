from __future__ import annotations

import argparse
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from ts_download_utils import (
    Progress,
    StateManifest,
    DownloadError,
    ensure_dir,
    get_tushare_token,
    iter_trade_dates_yyyymmdd,
    load_tushare_pro,
    read_stock_basic_codes,
    retry_call,
    stable_hash32,
    today_yyyymmdd,
    write_parquet_atomic,
)


def _safe_code(ts_code: str) -> str:
    return ts_code.replace(".", "_")


def _yyyymmdd_to_iso(d: str) -> str:
    return datetime.strptime(d, "%Y%m%d").strftime("%Y-%m-%d")


def _chunks(items: list[str], size: int) -> list[list[str]]:
    if size <= 0:
        return [items]
    return [items[i : i + size] for i in range(0, len(items), size)]


def _thread_local_pro():
    local = threading.local()
    token = get_tushare_token()

    def get():
        pro = getattr(local, "pro", None)
        if pro is None:
            pro = load_tushare_pro(token)
            local.pro = pro
        return pro

    return get


def run(
    *,
    raw_dir: Path,
    stock_basic: Path,
    start_date: str,
    end_date: str,
    freq: str,
    max_workers: int,
    overwrite: bool,
    shard_idx: int = 0,
    shard_count: int = 1,
    batch_size: int = 50,
) -> dict:
    pro = load_tushare_pro()
    trade_dates = iter_trade_dates_yyyymmdd(pro, start_date, end_date)
    if not trade_dates:
        return {"dataset": "stk_mins", "status": "no_dates"}

    # Group trade dates by month for better batching
    month_days: dict[str, list[str]] = {}
    for d in trade_dates:
        m = d[:6]
        month_days.setdefault(m, []).append(d)

    months = sorted(month_days.keys())
    ts_codes, list_date_by_code = read_stock_basic_codes(stock_basic)
    if shard_count > 1:
        ts_codes = [c for c in ts_codes if stable_hash32(c) % shard_count == shard_idx]
    
    out_dir = raw_dir / f"stk_mins_{freq}_parts"
    manifest_path = out_dir / "_manifest.json"
    ensure_dir(out_dir)
    
    manifest = StateManifest(manifest_path)

    if overwrite:
        for p in out_dir.rglob("*.parquet"):
            p.unlink()
        manifest.data = {}
        manifest.save()

    get_pro = _thread_local_pro()
    limit = 8000

    def _eligible_codes_for_month(m: str) -> list[str]:
        eligible: list[str] = []
        for code in ts_codes:
            list_date = list_date_by_code.get(code)
            if list_date:
                list_month = str(list_date)[:6]
                if m < list_month:
                    continue
            eligible.append(code)
        return sorted(eligible)

    tasks: list[tuple[str, int, list[str]]] = []
    for m in months:
        eligible = _eligible_codes_for_month(m)
        for bi, batch in enumerate(_chunks(eligible, int(batch_size))):
            task_key = f"{m}_b{bi:05d}"
            if manifest.is_done(task_key):
                continue
            tasks.append((m, bi, batch))

    progress = Progress(total=len(tasks), label=f"stk_mins_{freq}")

    def download_month_batch(m: str, batch_idx: int, codes: list[str]) -> int:
        task_key = f"{m}_b{batch_idx:05d}"
        pro2 = get_pro()
        rows_total = 0
        days = month_days.get(m, [])
        if not days:
            manifest.mark_done(task_key)
            return 0
            
        start_dt = f"{_yyyymmdd_to_iso(days[0])} 09:00:00"
        end_dt = f"{_yyyymmdd_to_iso(days[-1])} 19:00:00"

        offset = 0
        while True:
            def _call():
                return pro2.stk_mins(
                    ts_code=",".join(codes),
                    freq=freq,
                    start_date=start_dt,
                    end_date=end_dt,
                    limit=limit,
                    offset=offset,
                )

            df = retry_call(_call)
            if df is None or df.empty:
                break
            
            out_path = out_dir / f"{m}_b{batch_idx:05d}_o{offset:05d}.parquet"
            res = write_parquet_atomic(out_path, df)
            rows_total += res.rows
            got = int(df.shape[0])
            if got < limit:
                break
            offset += limit

        manifest.mark_done(task_key)
        return rows_total

    if tasks:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            fut_map = {ex.submit(download_month_batch, m, bi, b): (m, bi) for m, bi, b in tasks}
            for fut in as_completed(fut_map):
                m, bi = fut_map[fut]
                try:
                    rows = int(fut.result())
                    progress.update(done_inc=1, rows_inc=rows, msg=f"{m} b{bi:05d} 完成 rows={rows}")
                except Exception as e:
                    print(f"[stk_mins] {m} b{bi:05d} 失败: {e}")

    done_tasks = len([k for k in manifest.data if manifest.data[k]])
    return {
        "dataset": "stk_mins",
        "freq": freq,
        "months": months,
        "done_tasks": done_tasks,
        "parts_dir": str(out_dir),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--raw-dir", default=r"d:\Trading\data_ever_26_3_14\data\Raw_data")
    p.add_argument("--stock-basic", default=r"d:\Trading\data_ever_26_3_14\data\Raw_data\stock_basic.parquet")
    p.add_argument("--start-date", default="20100101")
    p.add_argument("--end-date", default=today_yyyymmdd())
    p.add_argument("--freq", default="60min")
    p.add_argument("--max-workers", type=int, default=4)
    p.add_argument("--batch-size", type=int, default=40)
    p.add_argument("--shard-idx", type=int, default=0)
    p.add_argument("--shard-count", type=int, default=1)
    p.add_argument("--overwrite", action="store_true")
    args = p.parse_args()
    res = run(
        raw_dir=Path(args.raw_dir),
        stock_basic=Path(args.stock_basic),
        start_date=str(args.start_date),
        end_date=str(args.end_date),
        freq=str(args.freq),
        max_workers=int(args.max_workers),
        overwrite=bool(args.overwrite),
        shard_idx=int(args.shard_idx),
        shard_count=int(args.shard_count),
        batch_size=int(args.batch_size),
    )
    print(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
