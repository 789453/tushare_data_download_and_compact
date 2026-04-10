from __future__ import annotations

import argparse
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from ts_download_utils import (
    Progress,
    StateManifest,
    ensure_dir,
    get_tushare_token,
    iter_trade_dates_yyyymmdd,
    load_tushare_pro,
    retry_call,
    today_yyyymmdd,
    write_parquet_atomic,
)


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
    api_name: str,
    raw_dir: Path,
    start_date: str,
    end_date: str,
    max_workers: int,
    overwrite: bool,
) -> dict:
    pro = load_tushare_pro()
    trade_dates = iter_trade_dates_yyyymmdd(pro, start_date, end_date)
    if not trade_dates:
        return {"dataset": api_name, "status": "no_dates"}

    # We use a single state manifest for the whole range
    out_dir = raw_dir / f"{api_name}_parts"
    manifest_path = out_dir / "_manifest.json"
    ensure_dir(out_dir)
    
    manifest = StateManifest(manifest_path)

    if overwrite:
        for p in out_dir.glob("*.parquet"):
            p.unlink()
        manifest.data = {}
        manifest.save()

    get_pro = _thread_local_pro()
    # Tushare limits vary, but most trade_date APIs return < 10000 rows per date
    limit = 6000 
    
    pending = [d for d in trade_dates if not manifest.is_done(d)]
    progress = Progress(total=len(pending), label=api_name)

    def download_one(d: str) -> int:
        t0 = time.time()
        rows = 0
        offset = 0
        pro2 = get_pro()
        api = getattr(pro2, api_name)
        while True:
            def _call():
                return api(trade_date=d, limit=limit, offset=offset)

            df = retry_call(_call)
            if df is None or df.empty:
                break
            
            # Save parts. For full re-download, we might want to group by year/month later.
            # For now, keeping it simple: one file per date per page.
            out_path = out_dir / f"{d}_o{offset:05d}.parquet"
            res = write_parquet_atomic(out_path, df)
            rows += res.rows
            got = int(df.shape[0])
            if got < limit:
                break
            offset += limit
            
        manifest.mark_done(d)
        return rows

    if pending:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            fut_map = {ex.submit(download_one, d): d for d in pending}
            for fut in as_completed(fut_map):
                d = fut_map[fut]
                try:
                    rows = int(fut.result())
                    progress.update(done_inc=1, rows_inc=rows, msg=f"{d} 完成 rows={rows}")
                except Exception as e:
                    print(f"[{api_name}] {d} 失败: {e}")

    done_cnt = len([d for d in trade_dates if manifest.is_done(d)])
    return {
        "dataset": api_name,
        "start": start_date,
        "end": end_date,
        "expected_dates": len(trade_dates),
        "done_dates": done_cnt,
        "parts_dir": str(out_dir),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("api", help="e.g. daily, daily_basic, moneyflow")
    p.add_argument("--raw-dir", default=r"d:\Trading\data_ever_26_3_14\data\Raw_data")
    p.add_argument("--start-date", default="20260101")
    p.add_argument("--end-date", default=today_yyyymmdd())
    p.add_argument("--max-workers", type=int, default=4)
    p.add_argument("--overwrite", action="store_true")
    args = p.parse_args()
    
    res = run(
        api_name=args.api,
        raw_dir=Path(args.raw_dir),
        start_date=str(args.start_date),
        end_date=str(args.end_date),
        max_workers=int(args.max_workers),
        overwrite=bool(args.overwrite),
    )
    print(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
