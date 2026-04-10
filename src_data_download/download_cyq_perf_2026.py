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
    load_tushare_pro,
    read_stock_basic_codes,
    retry_call,
    stable_hash32,
    today_yyyymmdd,
    write_parquet_atomic,
)


def _safe_code(ts_code: str) -> str:
    return ts_code.replace(".", "_")


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
    max_workers: int,
    overwrite: bool,
    shard_idx: int = 0,
    shard_count: int = 1,
) -> dict:
    ts_codes, _ = read_stock_basic_codes(stock_basic)
    if shard_count > 1:
        ts_codes = [c for c in ts_codes if stable_hash32(c) % shard_count == shard_idx]
    
    # Parts directory for general cyq_perf
    out_dir = raw_dir / "cyq_perf_parts"
    manifest_path = out_dir / "_manifest.json"
    ensure_dir(out_dir)
    
    manifest = StateManifest(manifest_path)

    if overwrite:
        for p in out_dir.rglob("*.parquet"):
            p.unlink()
        manifest.data = {}
        manifest.save()

    get_pro = _thread_local_pro()
    limit = 5000

    pending = [c for c in ts_codes if not manifest.is_done(c)]
    progress = Progress(total=len(pending), label="cyq_perf")

    def download_one(code: str) -> int:
        t0 = time.time()
        rows = 0
        offset = 0
        pro2 = get_pro()
        api = pro2.cyq_perf
        while True:
            def _call():
                return api(ts_code=code, start_date=start_date, end_date=end_date, limit=limit, offset=offset)

            df = retry_call(_call)
            if df is None or df.empty:
                break
            
            # Use safe code and offset for the filename
            # Note: We might want to include dates in the filename if downloading specific windows
            out_path = out_dir / f"{_safe_code(code)}_o{offset:05d}.parquet"
            res = write_parquet_atomic(out_path, df)
            rows += res.rows
            got = int(df.shape[0])
            
            if got < limit:
                break
            offset += limit
            
        manifest.mark_done(code)
        return rows

    if pending:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            fut_map = {ex.submit(download_one, c): c for c in pending}
            for fut in as_completed(fut_map):
                code = fut_map[fut]
                try:
                    rows = int(fut.result())
                    progress.update(done_inc=1, rows_inc=rows, msg=f"{code} 完成 rows={rows}")
                except Exception as e:
                    print(f"[cyq_perf] {code} 失败: {e}")

    done_cnt = len([c for c in ts_codes if manifest.is_done(c)])
    return {
        "dataset": "cyq_perf",
        "start": start_date,
        "end": end_date,
        "expected_codes": len(ts_codes),
        "done_codes": done_cnt,
        "parts_dir": str(out_dir),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--raw-dir", default=r"d:\Trading\data_ever_26_3_14\data\Raw_data")
    p.add_argument("--stock-basic", default=r"d:\Trading\data_ever_26_3_14\data\Raw_data\stock_basic.parquet")
    p.add_argument("--start-date", default="20180101")
    p.add_argument("--end-date", default=today_yyyymmdd())
    p.add_argument("--max-workers", type=int, default=2)
    p.add_argument("--shard-idx", type=int, default=0)
    p.add_argument("--shard-count", type=int, default=1)
    p.add_argument("--overwrite", action="store_true")
    args = p.parse_args()
    res = run(
        raw_dir=Path(args.raw_dir),
        stock_basic=Path(args.stock_basic),
        start_date=str(args.start_date),
        end_date=str(args.end_date),
        max_workers=int(args.max_workers),
        overwrite=bool(args.overwrite),
        shard_idx=int(args.shard_idx),
        shard_count=int(args.shard_count),
    )
    print(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
