from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .exceptions import StateStoreError
from .utils import now_iso_utc

TaskStatus = Literal["pending", "running", "done", "failed"]


@dataclass(frozen=True, slots=True)
class TaskState:
    task_key: str
    dataset: str
    params_hash: str
    status: TaskStatus
    rows: int | None = None
    updated_at: str | None = None
    latest_file: str | None = None
    error: str | None = None


class JsonStateStore:
    def __init__(self, path: Path):
        self.path = path
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._data = {}
            return
        try:
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(self._data, dict):
                self._data = {}
        except Exception as e:  # noqa: BLE001
            raise StateStoreError(f"无法读取 state 文件: {self.path}: {e}") from e

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        if self.path.exists():
            self.path.unlink()
        tmp.replace(self.path)

    def get(self, task_key: str) -> TaskState | None:
        obj = self._data.get(task_key)
        if obj is None:
            return None
        return TaskState(
            task_key=str(obj.get("task_key", task_key)),
            dataset=str(obj.get("dataset", "")),
            params_hash=str(obj.get("params_hash", "")),
            status=str(obj.get("status", "pending")),  # type: ignore[arg-type]
            rows=obj.get("rows", None),
            updated_at=obj.get("updated_at", None),
            latest_file=obj.get("latest_file", None),
            error=obj.get("error", None),
        )

    def is_done(self, task_key: str) -> bool:
        s = self.get(task_key)
        return s is not None and s.status == "done"

    def upsert(self, state: TaskState) -> None:
        self._data[state.task_key] = {
            "task_key": state.task_key,
            "dataset": state.dataset,
            "params_hash": state.params_hash,
            "status": state.status,
            "rows": state.rows,
            "updated_at": state.updated_at or now_iso_utc(),
            "latest_file": state.latest_file,
            "error": state.error,
        }
        self._save()

