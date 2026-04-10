from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from ts_download_utils import (
    DownloadError,
    iter_trade_dates_yyyymmdd,
    list_files_recursive,
    load_json,
    load_tushare_pro,
    today_yyyymmdd,
)


def _load_unique_dates(parquet_path: Path, col: str) -> set[str]:
    if not parquet_path.exists():
        raise DownloadError(f"文件不存在: {parquet_path}")
    df = pd.read_parquet(parquet_path, columns=[col])
    if df.empty:
        return set()
    return set(str(x) for x in df[col].dropna().unique().tolist())


def _count_rows(parquet_path: Path) -> int:
    try:
        import pyarrow.parquet as pq

        pf = pq.ParquetFile(parquet_path)
        return int(pf.metadata.num_rows)
    except Exception:  # noqa: BLE001
        df = pd.read_parquet(parquet_path, columns=[])
        return int(df.shape[0])


def verify_trade_date_coverage(
    *,
    name: str,
    parquet_path: Path,
    date_col: str,
    expected_dates: list[str],
) -> dict:
    got = _load_unique_dates(parquet_path, date_col)
    expected = set(expected_dates)
    missing = sorted(expected - got)
    extra = sorted(got - expected)
    rows = _count_rows(parquet_path)
    return {
        "dataset": name,
        "path": str(parquet_path),
        "rows": rows,
        "expected_dates": len(expected),
        "got_dates": len(got),
        "missing_dates": missing[:50],
        "missing_dates_cnt": len(missing),
        "extra_dates_cnt": len(extra),
    }


def verify_trade_date_parts(
    *,
    name: str,
    parts_dir: Path,
    expected_dates: list[str],
) -> dict:
    state_dir = parts_dir / "_state"
    expected = set(expected_dates)
    done_dates: dict[str, dict] = {}
    if state_dir.exists():
        for p in state_dir.glob("*.json"):
            obj = load_json(p)
            if isinstance(obj, dict) and "trade_date" in obj:
                done_dates[str(obj["trade_date"])] = obj
    done = set(done_dates.keys())
    missing = sorted(expected - done)
    total_rows = 0
    for v in done_dates.values():
        try:
            total_rows += int(v.get("rows", 0))
        except Exception:  # noqa: BLE001
            pass
    parts_files = len(list_files_recursive(parts_dir, suffix=".parquet"))
    return {
        "dataset": name,
        "parts_dir": str(parts_dir),
        "expected_dates": len(expected),
        "done_dates": len(done),
        "missing_dates_cnt": len(missing),
        "missing_dates": missing[:50],
        "parts_files": parts_files,
        "rows_from_state": total_rows,
    }


def verify_stk_mins(
    *,
    parquet_path: Path,
) -> dict:
    if not parquet_path.exists():
        raise DownloadError(f"文件不存在: {parquet_path}")
    cols = ["ts_code", "trade_time"]
    df = pd.read_parquet(parquet_path, columns=cols)
    rows = int(df.shape[0])
    codes = int(df["ts_code"].nunique()) if rows else 0
    days = 0
    if rows:
        trade_day = df["trade_time"].astype(str).str.slice(0, 10)
        days = int(trade_day.nunique())
    return {"dataset": "stk_mins", "path": str(parquet_path), "rows": rows, "codes": codes, "days": days}


def verify_stk_mins_parts(parts_dir: Path) -> dict:
    files = list_files_recursive(parts_dir, suffix=".parquet")
    codes = len([p for p in parts_dir.iterdir() if p.is_dir() and not p.name.startswith("_")]) if parts_dir.exists() else 0
    empty_markers = len(list(parts_dir.rglob("*.empty.json"))) if parts_dir.exists() else 0
    return {
        "dataset": "stk_mins",
        "parts_dir": str(parts_dir),
        "codes_dirs": codes,
        "parts_files": len(files),
        "empty_markers": empty_markers,
    }


def run(
    *,
    raw_dir: str,
    start_date: str,
    end_date: str,
    stk_mins_freq: str,
) -> list[dict]:
    pro = load_tushare_pro()
    expected_dates = iter_trade_dates_yyyymmdd(pro, start_date, end_date)
    if not expected_dates:
        raise DownloadError("交易日历为空")

    raw_dir_p = Path(raw_dir)
    year = str(start_date)[:4]

    reports: list[dict] = []
    for name in ("moneyflow", "daily_basic", "daily"):
        parts_dir = raw_dir_p / f"{name}_{year}_parts"
        single = raw_dir_p / f"{name}_{year}.parquet"
        if parts_dir.exists():
            reports.append(verify_trade_date_parts(name=name, parts_dir=parts_dir, expected_dates=expected_dates))
        if single.exists():
            reports.append(
                verify_trade_date_coverage(
                    name=f"{name}_single",
                    parquet_path=single,
                    date_col="trade_date",
                    expected_dates=expected_dates,
                )
            )

    cyq_parts = raw_dir_p / f"cyq_perf_{year}_parts"
    cyq_single = raw_dir_p / f"cyq_perf_{year}.parquet"
    if cyq_parts.exists():
        state_dir = cyq_parts / "_state"
        done_codes = len(list(state_dir.glob("*.json"))) if state_dir.exists() else 0
        parts_files = len(list_files_recursive(cyq_parts, suffix=".parquet"))
        reports.append({"dataset": "cyq_perf", "parts_dir": str(cyq_parts), "done_codes": done_codes, "parts_files": parts_files})
    if cyq_single.exists():
        rows = _count_rows(cyq_single)
        df = pd.read_parquet(cyq_single, columns=["ts_code", "trade_date"]) if rows else pd.DataFrame()
        codes = int(df["ts_code"].nunique()) if rows else 0
        days = int(df["trade_date"].nunique()) if rows else 0
        reports.append({"dataset": "cyq_perf_single", "path": str(cyq_single), "rows": rows, "codes": codes, "days": days})

    stk_parts = raw_dir_p / f"stk_mins_{year}_{stk_mins_freq}_parts"
    stk_single = raw_dir_p / f"stk_mins_{year}_{stk_mins_freq}.parquet"
    if stk_parts.exists():
        reports.append(verify_stk_mins_parts(stk_parts))
    if stk_single.exists():
        reports.append(verify_stk_mins(parquet_path=stk_single))

    return reports


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--raw-dir", default=r"d:\Trading\data_ever_26_3_14\data\Raw_data")
    p.add_argument("--start-date", default="20260101")
    p.add_argument("--end-date", default=today_yyyymmdd())
    p.add_argument("--stk-mins-freq", default="60min")
    args = p.parse_args()

    reports = run(
        raw_dir=str(args.raw_dir),
        start_date=str(args.start_date),
        end_date=str(args.end_date),
        stk_mins_freq=str(args.stk_mins_freq),
    )

    for r in reports:
        print(r)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
