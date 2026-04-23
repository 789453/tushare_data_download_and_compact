from __future__ import annotations

import logging
from pathlib import Path

from ..core.duckdb_store import DuckDBStore
from ..core.sqlite_meta import SQLiteMetaStore
from ..datasets.registry import REGISTRY
from .config_loader import load_storage_config


def run_verify_legacy_import(
    project_root: Path,
    datasets: list[str] | None = None,
):
    logger = logging.getLogger("tdc.jobs.verify_legacy")
    storage_cfg = load_storage_config(project_root)

    meta_store = SQLiteMetaStore(storage_cfg.sqlite_path)
    duckdb_store = DuckDBStore(storage_cfg.duckdb_path)

    target_datasets = datasets if datasets else list(REGISTRY.keys())

    from ..adapters.calendars import iter_trade_dates_yyyymmdd
    from ..core.utils import load_tushare_pro

    pro = load_tushare_pro()

    for ds_name in target_datasets:
        spec = REGISTRY.get(ds_name)
        if not spec or spec.asset_class != "stock":
            continue

        table_name = f"silver.fact_{spec.name}"
        # Check if table exists
        try:
            duckdb_store.query(f"SELECT count(*) FROM {table_name}")
        except Exception:
            continue

        logger.info(f"Verifying coverage for {ds_name} ({table_name})")

        if spec.date_col == "trade_date":
            df_got = duckdb_store.query(f"SELECT DISTINCT trade_date FROM {table_name} ORDER BY trade_date")
            if df_got.empty:
                logger.warning(f"{ds_name}: No data found in table")
                continue

            got_dates = set(df_got["trade_date"].astype(str).tolist())
            start_date = min(got_dates)
            end_date = max(got_dates)

            expected_dates = iter_trade_dates_yyyymmdd(pro, start_date, end_date)
            missing = sorted(set(expected_dates) - got_dates)

            logger.info(f"{ds_name}: Found {len(got_dates)} dates. Range: {start_date} to {end_date}")
            if missing:
                logger.warning(f"{ds_name}: Missing {len(missing)} trade dates: {missing[:10]}...")
            else:
                logger.info(f"{ds_name}: No missing dates in range")

        elif spec.date_col == "end_date":
            # For fina_indicator
            df_got = duckdb_store.query(f"SELECT DISTINCT end_date FROM {table_name} ORDER BY end_date")
            got_periods = sorted(df_got["end_date"].astype(str).tolist())
            logger.info(f"{ds_name}: Found {len(got_periods)} periods. Latest: {got_periods[-1] if got_periods else 'N/A'}")

    logger.info("Verification job finished")
