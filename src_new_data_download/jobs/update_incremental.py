from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from ..adapters.tushare_client import load_pro
from ..core.runner import Runner
from ..core.task_builders import CodeRangeTaskBuilder, PeriodTaskBuilder, SnapshotTaskBuilder, Task
from ..jobs.config_loader import load_runtime_config, load_storage_config, load_universe_config


def _today_yyyymmdd() -> str:
    return date.today().strftime("%Y%m%d")


def _add_months(yyyymm: str, delta: int) -> str:
    y = int(yyyymm[:4])
    m = int(yyyymm[4:6])
    idx = (y * 12 + (m - 1)) + int(delta)
    ny = idx // 12
    nm = idx % 12 + 1
    return f"{ny:04d}{nm:02d}"


def _to_quarter(yyyymmdd: str) -> str:
    y = int(yyyymmdd[:4])
    m = int(yyyymmdd[4:6])
    q = (m - 1) // 3 + 1
    return f"{y:04d}Q{q}"


def _add_quarters(yyyyq: str, delta: int) -> str:
    y = int(yyyyq[:4])
    q = int(yyyyq[-1])
    idx = (y * 4 + (q - 1)) + int(delta)
    ny = idx // 4
    nq = idx % 4 + 1
    return f"{ny:04d}Q{nq}"


def _latest_snapshot_dir(root: Path) -> Path | None:
    if not root.exists():
        return None
    cands: list[tuple[str, Path]] = []
    for p in root.iterdir():
        if not p.is_dir():
            continue
        name = p.name
        if name.startswith("snapshot_date="):
            cands.append((name.split("=", 1)[1], p))
    if not cands:
        return None
    return sorted(cands, key=lambda x: x[0])[-1][1]


def _load_latest_snapshot_parquet(snapshot_root: Path) -> "object | None":
    import pandas as pd

    d = _latest_snapshot_dir(snapshot_root)
    if d is None:
        return None
    f = d / "part-000.parquet"
    if not f.exists():
        return None
    return pd.read_parquet(f)


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]
    storage = load_storage_config(project_root)
    runtime = load_runtime_config(project_root)
    universe = load_universe_config(project_root)

    p = argparse.ArgumentParser()
    p.add_argument("--raw-root", default=str(storage.raw_root))
    p.add_argument("--state-path", default=str(storage.state_path))
    p.add_argument("--start-date", default="")
    p.add_argument("--end-date", default=_today_yyyymmdd())
    p.add_argument("--start-m", default="")
    p.add_argument("--end-m", default="")
    p.add_argument("--start-q", default="")
    p.add_argument("--end-q", default="")
    p.add_argument("--max-workers", type=int, default=int(runtime.max_workers))
    p.add_argument("--compression", default=str(runtime.compression))
    p.add_argument("--datasets", default="index,index_basic,futures,options,macro,fx")
    p.add_argument("--overwrite", action="store_true")
    args = p.parse_args()

    raw_root = Path(args.raw_root)
    state_path = Path(args.state_path)
    raw_root.mkdir(parents=True, exist_ok=True)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    end_date = str(args.end_date)
    start_date = str(args.start_date) or end_date

    if not args.end_m:
        end_m = end_date[:6]
    else:
        end_m = str(args.end_m)
    if not args.start_m:
        start_m = _add_months(end_m, -24)
    else:
        start_m = str(args.start_m)

    if not args.end_q:
        end_q = _to_quarter(end_date)
    else:
        end_q = str(args.end_q)
    if not args.start_q:
        start_q = _add_quarters(end_q, -8)
    else:
        start_q = str(args.start_q)

    datasets = set(x.strip() for x in str(args.datasets).split(",") if x.strip())

    pro = load_pro()
    runner = Runner(
        project_root=project_root,
        raw_root=raw_root,
        state_path=state_path,
        compression=str(args.compression),
    )

    snapshot_tasks = []
    snapshot_builder = SnapshotTaskBuilder()

    if "index_basic" in datasets:
        from ..datasets.index_basic import SPEC as INDEX_BASIC

        INDEX_BASIC.validate()
        snapshot_tasks.extend(snapshot_builder.build(pro, INDEX_BASIC, params={}))

    if "futures" in datasets:
        from ..datasets.cffex_fut_basic import SPEC as FUT_BASIC

        FUT_BASIC.validate()
        snapshot_tasks.extend(snapshot_builder.build(pro, FUT_BASIC, params={}))

    if "options" in datasets:
        from ..datasets.cffex_opt_basic import SPEC as OPT_BASIC

        OPT_BASIC.validate()
        snapshot_tasks.extend(snapshot_builder.build(pro, OPT_BASIC, params={}))

    if "fx" in datasets:
        from ..datasets.fx_basic import SPEC as FX_BASIC

        FX_BASIC.validate()
        snapshot_tasks.extend(snapshot_builder.build(pro, FX_BASIC, params={}))

    if snapshot_tasks:
        runner.run(pro=pro, tasks=snapshot_tasks, max_workers=1, overwrite=bool(args.overwrite))

    tasks = []

    if "index" in datasets:
        from ..datasets.index_daily import SPEC as INDEX_DAILY
        from ..datasets.index_dailybasic import SPEC as INDEX_DAILYBASIC
        from ..datasets.index_weekly import SPEC as INDEX_WEEKLY

        INDEX_DAILY.validate()
        INDEX_DAILYBASIC.validate()
        INDEX_WEEKLY.validate()

        code_builder = CodeRangeTaskBuilder(window="year")
        tasks.extend(code_builder.build(pro, INDEX_DAILY, ts_codes=universe.core_indices, start_date=start_date, end_date=end_date))
        tasks.extend(
            code_builder.build(
                pro,
                INDEX_DAILYBASIC,
                ts_codes=universe.core_index_dailybasic_supported,
                start_date=start_date,
                end_date=end_date,
            )
        )
        tasks.extend(code_builder.build(pro, INDEX_WEEKLY, ts_codes=universe.core_indices, start_date=start_date, end_date=end_date))

    if "index_global" in datasets:
        from ..datasets.index_global import SPEC as INDEX_GLOBAL

        INDEX_GLOBAL.validate()
        code_builder = CodeRangeTaskBuilder(window="year")
        tasks.extend(code_builder.build(pro, INDEX_GLOBAL, ts_codes=universe.core_global_indices, start_date=start_date, end_date=end_date))

    if "daily_info" in datasets:
        from ..datasets.daily_info import SPEC as DAILY_INFO

        DAILY_INFO.validate()
        for ex in ("SZ", "SH"):
            tasks.append(Task(spec=DAILY_INFO, request_params={"trade_date": end_date, "exchange": ex}))

    if "macro" in datasets:
        from ..datasets.macro_gdp import SPEC as MACRO_GDP
        from ..datasets.macro_cpi import SPEC as MACRO_CPI
        from ..datasets.macro_ppi import SPEC as MACRO_PPI
        from ..datasets.macro_money_supply import SPEC as MACRO_M
        from ..datasets.macro_social_financing import SPEC as MACRO_SF
        from ..datasets.macro_pmi import SPEC as MACRO_PMI

        for s in (MACRO_GDP, MACRO_CPI, MACRO_PPI, MACRO_M, MACRO_SF, MACRO_PMI):
            s.validate()

        period_builder = PeriodTaskBuilder()
        tasks.extend(period_builder.build(pro, MACRO_GDP, start=start_q, end=end_q))
        for s in (MACRO_CPI, MACRO_PPI, MACRO_M, MACRO_SF, MACRO_PMI):
            tasks.extend(period_builder.build(pro, s, start=start_m, end=end_m))

    if "futures" in datasets:
        from ..datasets.cffex_fut_daily import SPEC as FUT_DAILY
        from ..datasets.cffex_fut_mapping import SPEC as FUT_MAPPING

        FUT_DAILY.validate()
        FUT_MAPPING.validate()

        df_basic = _load_latest_snapshot_parquet(raw_root / "futures" / "cffex_fut_basic")
        fut_codes: list[str] = []
        if df_basic is not None and "ts_code" in df_basic.columns:
            for x in df_basic["ts_code"].dropna().unique().tolist():
                s = str(x)
                if any(s.startswith(pfx) for pfx in universe.core_cffex_futures_prefix):
                    fut_codes.append(s)
        fut_codes = sorted(set(fut_codes))
        if fut_codes:
            code_builder = CodeRangeTaskBuilder(window="year")
            tasks.extend(code_builder.build(pro, FUT_DAILY, ts_codes=fut_codes, start_date=start_date, end_date=end_date))
            tasks.extend(code_builder.build(pro, FUT_MAPPING, ts_codes=fut_codes, start_date=start_date, end_date=end_date))

    if "options" in datasets:
        from ..datasets.cffex_opt_daily import SPEC as OPT_DAILY

        OPT_DAILY.validate()

        df_opt = _load_latest_snapshot_parquet(raw_root / "options" / "cffex_opt_basic")
        opt_codes: list[str] = []
        if df_opt is not None and "ts_code" in df_opt.columns:
            for x in df_opt["ts_code"].dropna().unique().tolist():
                s = str(x)
                if any(s.startswith(pfx) for pfx in universe.core_cffex_options_prefix):
                    opt_codes.append(s)
        opt_codes = sorted(set(opt_codes))
        if opt_codes:
            code_builder = CodeRangeTaskBuilder(window="year")
            tasks.extend(code_builder.build(pro, OPT_DAILY, ts_codes=opt_codes, start_date=start_date, end_date=end_date))

    if "fx" in datasets:
        from ..datasets.fx_daily import SPEC as FX_DAILY

        FX_DAILY.validate()

        df_fx = _load_latest_snapshot_parquet(raw_root / "fx" / "fx_basic")
        fx_codes: list[str] = []
        if df_fx is not None and "ts_code" in df_fx.columns:
            for x in df_fx["ts_code"].dropna().unique().tolist():
                s = str(x)
                if any(sym in s for sym in universe.core_fx_symbols):
                    fx_codes.append(s)
        if not fx_codes:
            fx_codes = list(universe.core_fx_symbols)
        fx_codes = sorted(set(fx_codes))
        code_builder = CodeRangeTaskBuilder(window="year")
        tasks.extend(code_builder.build(pro, FX_DAILY, ts_codes=fx_codes, start_date=start_date, end_date=end_date))

    results = runner.run(pro=pro, tasks=tasks, max_workers=int(args.max_workers), overwrite=bool(args.overwrite))
    for r in sorted(results, key=lambda x: (x.dataset, x.task_key)):
        print(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
