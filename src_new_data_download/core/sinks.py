from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .lineage import LineageWriter


@dataclass(frozen=True, slots=True)
class SinkWriteResult:
    parquet_path: Path
    meta_path: Path
    rows: int
    columns: list[str]


class ParquetSink:
    def __init__(self, *, project_root: Path, compression: str = "zstd"):
        self.project_root = project_root
        self.compression = compression
        self._lineage = LineageWriter(project_root=project_root)

    def write(
        self,
        parquet_path: Path,
        df: "object",
        *,
        dataset: str,
        api_name: str,
        task_key: str,
        request_params: dict,
    ) -> SinkWriteResult:
        from .utils import write_parquet_atomic

        r = write_parquet_atomic(parquet_path, df, compression=self.compression)  # type: ignore[arg-type]
        cols = [str(x) for x in getattr(df, "columns", [])]
        meta_path = self._lineage.write_sidecar(
            parquet_path,
            dataset=dataset,
            api_name=api_name,
            task_key=task_key,
            request_params=request_params,
            rows=int(r.rows),
            columns=cols,
        )
        return SinkWriteResult(parquet_path=Path(r.path), meta_path=meta_path, rows=int(r.rows), columns=cols)

