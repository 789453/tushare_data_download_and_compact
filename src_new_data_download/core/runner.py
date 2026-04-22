from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from .dataset_spec import DatasetSpec
from .exceptions import DownloadError
from .sinks import ParquetSink
from .state_store import JsonStateStore, TaskState
from .task_builders import Task


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
        state_path: Path,
        compression: str = "zstd",
    ):
        self.project_root = project_root
        self.raw_root = raw_root
        self.state = JsonStateStore(state_path)
        self.sink = ParquetSink(project_root=project_root, compression=compression)

    def _task_output_path(self, task: Task) -> Path:
        from ..ts_download_utils import today_yyyymmdd

        parts: list[str] = [task.spec.asset_class, task.spec.name]
        for col in task.spec.partition_cols:
            v = task.request_params.get(col, None)
            if v is None and col == "snapshot_date":
                v = today_yyyymmdd()
            if v is None:
                continue
            parts.append(f"{col}={v}")
        parts.append("part-000.parquet")
        return self.raw_root.joinpath(*parts)

    def _fetch_df(self, pro, spec: DatasetSpec, request_params: dict):
        from ..ts_download_utils import paginated_fetch

        params = dict(request_params)
        if spec.exchange_filter and "exchange" not in params:
            params["exchange"] = spec.exchange_filter
        if spec.market_filter and "market" not in params:
            params["market"] = spec.market_filter

        frames = list(
            paginated_fetch(
                pro,
                spec.api_name,
                limit=int(spec.limit),
                params=params,
            )
        )
        if not frames:
            import pandas as pd

            return pd.DataFrame()
        import pandas as pd

        return pd.concat(frames, ignore_index=True)

    def run(self, *, pro, tasks: list[Task], max_workers: int = 4, overwrite: bool = False) -> list[TaskRunResult]:
        self.raw_root.mkdir(parents=True, exist_ok=True)

        def _run_one(t: Task) -> TaskRunResult:
            if (not overwrite) and self.state.is_done(t.task_key):
                s = self.state.get(t.task_key)
                return TaskRunResult(
                    task_key=t.task_key,
                    dataset=t.spec.name,
                    status="skipped",
                    rows=int(s.rows or 0) if s else 0,
                    parquet_path=s.latest_file if s else None,
                )

            self.state.upsert(
                TaskState(
                    task_key=t.task_key,
                    dataset=t.spec.name,
                    params_hash=t.params_hash,
                    status="running",
                    rows=None,
                    latest_file=None,
                )
            )

            try:
                df = self._fetch_df(pro, t.spec, t.request_params)
                out_path = self._task_output_path(t)
                if df is None or df.empty:
                    self.state.upsert(
                        TaskState(
                            task_key=t.task_key,
                            dataset=t.spec.name,
                            params_hash=t.params_hash,
                            status="done",
                            rows=0,
                            latest_file=None,
                        )
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
                self.state.upsert(
                    TaskState(
                        task_key=t.task_key,
                        dataset=t.spec.name,
                        params_hash=t.params_hash,
                        status="done",
                        rows=int(r.rows),
                        latest_file=str(r.parquet_path),
                    )
                )
                return TaskRunResult(
                    task_key=t.task_key,
                    dataset=t.spec.name,
                    status="done",
                    rows=int(r.rows),
                    parquet_path=str(r.parquet_path),
                )
            except Exception as e:  # noqa: BLE001
                self.state.upsert(
                    TaskState(
                        task_key=t.task_key,
                        dataset=t.spec.name,
                        params_hash=t.params_hash,
                        status="failed",
                        rows=None,
                        latest_file=None,
                        error=str(e),
                    )
                )
                raise

        if max_workers <= 1:
            return [_run_one(t) for t in tasks]

        results: list[TaskRunResult] = []
        with ThreadPoolExecutor(max_workers=int(max_workers)) as ex:
            futs = [ex.submit(_run_one, t) for t in tasks]
            for fut in as_completed(futs):
                results.append(fut.result())
        return results

