from __future__ import annotations

import argparse
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from ts_download_utils import (
    Progress,
    ensure_dir,
    get_tushare_token,
    iter_trade_dates_yyyymmdd,
    load_tushare_pro,
    retry_call,
    save_json,
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
    raw_dir: Path,
    start_date: str,
    end_date: str,
    max_workers: int,
    overwrite: bool,
) -> dict:
    pro = load_tushare_pro()
    trade_dates = iter_trade_dates_yyyymmdd(pro, start_date, end_date)
    year = start_date[:4]

    out_dir = raw_dir / f"moneyflow_{year}_parts"
    state_dir = out_dir / "_state"
    ensure_dir(out_dir)
    ensure_dir(state_dir)

    if overwrite:
        for p in out_dir.glob("*.parquet"):
            p.unlink()
        for p in state_dir.glob("*.json"):
            p.unlink()

    get_pro = _thread_local_pro()
    limit = 6000

    def done_marker(d: str) -> Path:
        return state_dir / f"{d}.json"

    def already_done(d: str) -> bool:
        return done_marker(d).exists()

    pending = [d for d in trade_dates if not already_done(d)]
    progress = Progress(total=len(pending), label="moneyflow")

    def download_one(d: str) -> int:
        t0 = time.time()
        pages = 0
        rows = 0
        offset = 0
        pro2 = get_pro()
        api = pro2.moneyflow
        while True:
            def _call():
                return api(trade_date=d, limit=limit, offset=offset)

            df = retry_call(_call)
            if df is None or df.empty:
                break
            res = write_parquet_atomic(out_dir / f"{d}_o{offset:05d}.parquet", df)
            rows += res.rows
            pages += 1
            got = int(df.shape[0])
            if got < limit:
                break
            offset += limit
        save_json(done_marker(d), {"trade_date": d, "rows": rows, "pages": pages, "seconds": round(time.time() - t0, 3)})
        return rows

    if pending:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            fut_map = {ex.submit(download_one, d): d for d in pending}
            for fut in as_completed(fut_map):
                d = fut_map[fut]
                rows = int(fut.result())
                progress.update(done_inc=1, rows_inc=rows, msg=f"{d} 完成 rows={rows}")

    done_cnt = len([d for d in trade_dates if already_done(d)])
    return {
        "dataset": "moneyflow",
        "year": year,
        "expected_dates": len(trade_dates),
        "done_dates": done_cnt,
        "missing_dates": len(trade_dates) - done_cnt,
        "parts_dir": str(out_dir),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--raw-dir", default=r"d:\Trading\data_ever_26_3_14\data\Raw_data")
    p.add_argument("--start-date", default="20100101")
    p.add_argument("--end-date", default=today_yyyymmdd())
    p.add_argument("--max-workers", type=int, default=4)
    p.add_argument("--overwrite", action="store_true")
    args = p.parse_args()
    res = run(
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

