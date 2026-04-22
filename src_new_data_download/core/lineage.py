from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .utils import canonical_json, sha256_file, try_read_git_sha


def now_iso_cst() -> str:
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).isoformat()


@dataclass(frozen=True, slots=True)
class LineageRecord:
    dataset: str
    api_name: str
    task_key: str
    request_params: dict
    fetched_at: str
    rows: int
    columns: list[str]
    code_version: str | None
    checksum: str


class LineageWriter:
    def __init__(self, *, project_root: Path):
        self.project_root = project_root

    def write_sidecar(
        self,
        parquet_path: Path,
        *,
        dataset: str,
        api_name: str,
        task_key: str,
        request_params: dict,
        rows: int,
        columns: list[str],
    ) -> Path:
        meta_path = parquet_path.with_suffix(parquet_path.suffix + ".meta.json")
        record = LineageRecord(
            dataset=dataset,
            api_name=api_name,
            task_key=task_key,
            request_params=request_params,
            fetched_at=now_iso_cst(),
            rows=int(rows),
            columns=list(columns),
            code_version=try_read_git_sha(self.project_root),
            checksum=f"sha256:{sha256_file(parquet_path)}",
        )
        meta_path.write_text(canonical_json(asdict(record)), encoding="utf-8")
        return meta_path
