from __future__ import annotations

import logging
import uuid
from pathlib import Path

from ..core.dataset_spec import DatasetSpec
from ..core.runner import Runner
from ..core.sqlite_meta import SQLiteMetaStore
from ..core.duckdb_store import DuckDBStore
from ..core.rate_limiter import GlobalRateLimiter
from ..core.task_builders import TradeDateTaskBuilder, CodeRangeTaskBuilder, SnapshotTaskBuilder, PeriodTaskBuilder
from .config_loader import load_storage_config, load_runtime_config, load_universe_config
from ..datasets.registry import REGISTRY


from concurrent.futures import ThreadPoolExecutor, as_completed

def run_incremental(
    project_root: Path,
    dataset_names: list[str] | None = None,
    max_dataset_workers: int = 4,
    max_task_workers: int = 4,
):
    logger = logging.getLogger("tdc.jobs.update_incremental")
    
    storage_cfg = load_storage_config(project_root)
    runtime_cfg = load_runtime_config(project_root)
    universe_cfg = load_universe_config(project_root)
    
    meta_store = SQLiteMetaStore(storage_cfg.sqlite_path)
    duckdb_store = DuckDBStore(storage_cfg.duckdb_path)
    rate_limiter = GlobalRateLimiter()
    
    # Configure rate limits based on Tushare common constraints
    rate_limiter.set_rate("daily", 200)
    rate_limiter.set_rate("daily_basic", 200)
    rate_limiter.set_rate("index_daily", 100)
    rate_limiter.set_rate("fut_daily", 100)
    rate_limiter.set_rate("opt_daily", 100)
    rate_limiter.set_rate("fx_daily", 100)
    
    runner = Runner(
        project_root=project_root,
        raw_root=storage_cfg.raw_root,
        meta_store=meta_store,
        rate_limiter=rate_limiter,
        logger=logger,
        compression=runtime_cfg.compression
    )
    
    from ..core.utils import load_tushare_pro, today_yyyymmdd
    pro = load_tushare_pro()
    
    job_id = str(uuid.uuid4())
    meta_store.create_job_run(job_id, "update_incremental")
    
    target_datasets = dataset_names if dataset_names else list(REGISTRY.keys())
    today = today_yyyymmdd()

    def _process_one_dataset(name: str):
        spec = REGISTRY.get(name)
        if not spec:
            logger.warning(f"Dataset {name} not found in registry")
            return
            
        logger.info(f"Starting incremental update for {name}")
        
        # Start date logic: Stock from 2026, Others from 2018
        default_start = "20260101" if spec.asset_class == "stock" else "20180101"
        watermark = meta_store.get_watermark(name) or spec.stable_before or default_start
        
        tasks = []
        try:
            if spec.fetch_mode == "trade_date":
                builder = TradeDateTaskBuilder()
                tasks = builder.build(pro, spec, start_date=watermark, end_date=today)
            elif spec.fetch_mode == "ts_code_range":
                builder = CodeRangeTaskBuilder()
                codes = []
                if spec.asset_class == "index":
                    codes = universe_cfg.core_indices
                elif spec.asset_class == "futures":
                    codes = universe_cfg.core_cffex_futures_selected
                elif spec.asset_class == "fx":
                    codes = universe_cfg.core_fx_selected
                elif spec.asset_class == "options":
                    # Special case: load all codes from catalog for options daily
                    catalog_path = storage_cfg.catalog_root / "opt_basic_cffex.parquet"
                    if catalog_path.exists():
                        df_opt = duckdb_store.query(f"SELECT ts_code FROM read_parquet('{catalog_path}')")
                        codes = df_opt["ts_code"].tolist()
                    else:
                        logger.warning(f"Catalog {catalog_path} not found, skipping {name}")
                        return
                
                if spec.selected_codes:
                    codes = list(spec.selected_codes)
                
                tasks = builder.build(pro, spec, ts_codes=codes, start_date=watermark, end_date=today)
            elif spec.fetch_mode == "snapshot":
                builder = SnapshotTaskBuilder()
                tasks = builder.build(pro, spec, params={"snapshot_date": today})
            elif spec.fetch_mode.startswith("period"):
                builder = PeriodTaskBuilder()
                tasks = builder.build(pro, spec, start=watermark[:6], end=today[:6])
            
            if not tasks:
                logger.info(f"No tasks for {name}")
                return
                
            results = runner.run_tasks(pro=pro, job_id=job_id, tasks=tasks, max_workers=max_task_workers)
            
            done_paths = [r.parquet_path for r in results if r.status == "done" and r.parquet_path]
            if done_paths:
                duckdb_store.merge_incremental(spec, done_paths)
                meta_store.update_watermark(name, today, spec.date_col or "trade_date")
                
                silver_path = storage_cfg.silver_root / f"{name}.parquet"
                duckdb_store.export_silver_parquet(spec, silver_path)
                meta_store.record_file(str(silver_path), name, None, "silver_export")
                
            logger.info(f"Finished {name}: {len(done_paths)} tasks succeeded")
        except Exception as e:
            logger.exception(f"Failed to process dataset {name}: {e}")

    # Use ThreadPoolExecutor for dataset-level parallelism
    with ThreadPoolExecutor(max_workers=int(max_dataset_workers)) as ex:
        futures = [ex.submit(_process_one_dataset, name) for name in target_datasets]
        for fut in as_completed(futures):
            fut.result()
            
    meta_store.update_job_status(job_id, "done")
    logger.info(f"Incremental update job {job_id} finished")
