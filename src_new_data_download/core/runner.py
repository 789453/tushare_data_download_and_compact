import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from .dataset_spec import DatasetSpec
from .exceptions import DownloadError
from .sinks import ParquetSink
from .sqlite_meta import SQLiteMetaStore
from .task_builders import Task
from .rate_limiter import GlobalRateLimiter


@dataclass(frozen=True, slots=True)
class TaskRunResult:
    task_key: str
    dataset: str
    status: str
    rows: int
    parquet_path: str | None


class Runner:
    def __init__(
        self,
        *,
        project_root: Path,
        raw_root: Path,
        meta_store: SQLiteMetaStore,
        rate_limiter: GlobalRateLimiter,
        logger: logging.Logger | None = None,
        compression: str = "zstd",
    ):
        self.project_root = project_root
        self.raw_root = raw_root
        self.meta_store = meta_store
        self.rate_limiter = rate_limiter
        self.logger = logger or logging.getLogger(__name__)
        self.sink = ParquetSink(project_root=project_root, compression=compression)

    def _task_output_path(self, task: Task) -> Path:
        from .utils import today_yyyymmdd

        parts: list[str] = [task.spec.asset_class, task.spec.name]
        
        # Follow the README partition strategy
        # data/raw/index/index_daily_selected/ts_code=399300.SZ/year=2024/399300.SH_20240101_20241231_0001.parquet
        
        for col in task.spec.partition_cols:
            v = task.request_params.get(col, None)
            if v is None and col == "snapshot_date":
                v = today_yyyymmdd()
            if v is not None:
                parts.append(f"{col}={v}")
        
        # Add a filename based on params
        filename_parts = []
        for k, v in sorted(task.request_params.items()):
            filename_parts.append(f"{v}")
        
        if not filename_parts:
            filename_parts.append("part")
        
        filename = "_".join(filename_parts) + "_000.parquet"
        parts.append(filename)
        
        return self.raw_root.joinpath(*parts)

    def _fetch_df(self, pro, spec: DatasetSpec, request_params: dict):
        from .utils import paginated_fetch

        params = dict(request_params)
        if spec.exchange_filter and "exchange" not in params:
            params["exchange"] = spec.exchange_filter
        if spec.market_filter and "market" not in params:
            params["market"] = spec.market_filter

        # Apply rate limiting
        self.rate_limiter.wait(spec.api_name)

        frames = [
            df
            for df in paginated_fetch(
                pro,
                spec.api_name,
                limit=int(spec.limit),
                params=params,
            )
            if df is not None and not df.empty
        ]
        
        if not frames:
            import pandas as pd
            return pd.DataFrame()
        
        import pandas as pd
        return pd.concat(frames, ignore_index=True)

    def run_tasks(self, *, pro, job_id: str, tasks: list[Task], max_workers: int = 4, overwrite: bool = False) -> list[TaskRunResult]:
        self.raw_root.mkdir(parents=True, exist_ok=True)

        def _run_one(t: Task) -> TaskRunResult:
            if (not overwrite) and self.meta_store.is_task_done(t.task_key):
                # We still need some basic info to return
                return TaskRunResult(
                    task_key=t.task_key,
                    dataset=t.spec.name,
                    status="skipped",
                    rows=0,
                    parquet_path=None,
                )

            self.meta_store.upsert_task_run(
                task_key=t.task_key,
                job_id=job_id,
                dataset_name=t.spec.name,
                params=t.request_params,
                params_hash=t.params_hash,
                status="running"
            )

            try:
                df = self._fetch_df(pro, t.spec, t.request_params)
                out_path = self._task_output_path(t)
                
                if df is None or df.empty:
                    self.meta_store.upsert_task_run(
                        task_key=t.task_key,
                        job_id=job_id,
                        dataset_name=t.spec.name,
                        params=t.request_params,
                        params_hash=t.params_hash,
                        status="done",
                        rows_written=0
                    )
                    return TaskRunResult(task_key=t.task_key, dataset=t.spec.name, status="done", rows=0, parquet_path=None)

                r = self.sink.write(
                    out_path,
                    df,
                    dataset=t.spec.name,
                    api_name=t.spec.api_name,
                    task_key=t.task_key,
                    request_params=t.request_params,
                )
                
                self.meta_store.upsert_task_run(
                    task_key=t.task_key,
                    job_id=job_id,
                    dataset_name=t.spec.name,
                    params=t.request_params,
                    params_hash=t.params_hash,
                    status="done",
                    rows_written=int(r.rows),
                    parquet_path=str(r.parquet_path)
                )
                
                # Also record file in manifest
                self.meta_store.record_file(
                    file_path=str(r.parquet_path),
                    dataset_name=t.spec.name,
                    task_key=t.task_key,
                    file_kind="raw_part",
                    row_count=int(r.rows)
                )

                return TaskRunResult(
                    task_key=t.task_key,
                    dataset=t.spec.name,
                    status="done",
                    rows=int(r.rows),
                    parquet_path=str(r.parquet_path),
                )
            except Exception as e:
                self.logger.error(f"Task {t.task_key} failed: {e}")
                self.meta_store.upsert_task_run(
                    task_key=t.task_key,
                    job_id=job_id,
                    dataset_name=t.spec.name,
                    params=t.request_params,
                    params_hash=t.params_hash,
                    status="failed",
                    error_message=str(e)
                )
                return TaskRunResult(
                    task_key=t.task_key,
                    dataset=t.spec.name,
                    status="failed",
                    rows=0,
                    parquet_path=None
                )

        if max_workers <= 1:
            return [_run_one(t) for t in tasks]

        results: list[TaskRunResult] = []
        with ThreadPoolExecutor(max_workers=int(max_workers)) as ex:
            futs = [ex.submit(_run_one, t) for t in tasks]
            for fut in as_completed(futs):
                results.append(fut.result())
        return results

