from __future__ import annotations

import logging
import uuid
from pathlib import Path

from ..core.duckdb_store import DuckDBStore
from ..core.sqlite_meta import SQLiteMetaStore
from ..datasets.registry import REGISTRY
from .config_loader import load_storage_config, load_universe_config


def run_import_legacy_stock_raw(
    project_root: Path,
    datasets: list[str] | None = None,
    overwrite_silver: bool = False,
):
    logger = logging.getLogger("tdc.jobs.import_legacy")
    storage_cfg = load_storage_config(project_root)
    universe_cfg = load_universe_config(project_root)

    if not universe_cfg.stock_import_legacy.enabled:
        logger.info("Legacy import is disabled in config")
        return

    meta_store = SQLiteMetaStore(storage_cfg.sqlite_path)
    duckdb_store = DuckDBStore(storage_cfg.duckdb_path)

    legacy_files = universe_cfg.stock_import_legacy.files
    source_root = universe_cfg.stock_import_legacy.source_root

    target_datasets = datasets if datasets else list(legacy_files.keys())

    job_id = str(uuid.uuid4())
    meta_store.create_job_run(job_id, "legacy_import", total_tasks=len(target_datasets))

    for ds_name in target_datasets:
        if ds_name not in legacy_files:
            logger.warning(f"Dataset {ds_name} not in legacy import config")
            continue

        spec = REGISTRY.get(ds_name)
        if not spec:
            logger.warning(f"Dataset {ds_name} not in registry")
            continue

        filename = legacy_files[ds_name]
        source_path = source_root / filename

        if not source_path.exists():
            logger.error(f"Legacy source {source_path} not found: {source_path}")
            continue

        logger.info(f"Importing legacy dataset: {ds_name} from {source_path}")

        try:
            # 1. Record source file
            import os

            stat = os.stat(source_path)
            meta_store.record_file(
                file_path=str(source_path),
                dataset_name=ds_name,
                task_key=None,
                file_kind="legacy_source",
                file_size=stat.st_size,
            )

            # 2. Merge into DuckDB silver
            duckdb_store.merge_incremental(spec, [str(source_path)])

            # 3. Export to silver parquet
            silver_path = storage_cfg.silver_root / f"{ds_name}.parquet"
            if overwrite_silver or not silver_path.exists():
                duckdb_store.export_silver_parquet(spec, silver_path)

            # 4. Update watermark based on date_col
            if spec.date_col:
                table_name = f"silver.fact_{spec.name}"
                res = duckdb_store.query(f"SELECT MAX({spec.date_col}) as max_val FROM {table_name}")
                if not res.empty:
                    max_val = res.iloc[0]["max_val"]
                    if max_val:
                        # If it's trade_time, take first 8 chars
                        watermark = str(max_val)[:8] if "time" in spec.date_col else str(max_val)
                        meta_store.update_watermark(ds_name, watermark, spec.date_col)
                        logger.info(f"Updated watermark for {ds_name} to {watermark}")

            # 5. Record export file
            if silver_path.exists():
                stat_silver = os.stat(silver_path)
                meta_store.record_file(
                    file_path=str(silver_path),
                    dataset_name=ds_name,
                    task_key=None,
                    file_kind="silver_export",
                    file_size=stat_silver.st_size,
                )

            meta_store.update_job_status(job_id, "running", done_tasks=1)
            logger.info(f"Successfully imported {ds_name}")

        except Exception as e:
            logger.exception(f"Failed to import {ds_name}: {e}")
            meta_store.update_job_status(job_id, "running", failed_tasks=1)

    meta_store.update_job_status(job_id, "done")
    logger.info("Legacy import job finished")
