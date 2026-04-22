from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .dataset_spec import DatasetSpec
from .exceptions import TaskBuildError
from .utils import canonical_json, sha1_text


@dataclass(frozen=True, slots=True)
class Task:
    spec: DatasetSpec
    request_params: dict

    @property
    def task_key(self) -> str:
        return sha1_text(f"{self.spec.name}|{canonical_json(self.request_params)}")

    @property
    def params_hash(self) -> str:
        return sha1_text(canonical_json(self.request_params))


class TradeDateTaskBuilder:
    def build(self, pro, spec: DatasetSpec, *, start_date: str, end_date: str) -> list[Task]:
        from ..ts_download_utils import iter_trade_dates_yyyymmdd

        if spec.date_col is None:
            raise TaskBuildError(f"{spec.name}: trade_date 模式必须提供 date_col")
        dates = iter_trade_dates_yyyymmdd(pro, start_date=start_date, end_date=end_date)
        tasks: list[Task] = []
        for d in dates:
            tasks.append(Task(spec=spec, request_params={spec.date_col: d}))
        return tasks


def _iter_year_windows(start_date: str, end_date: str) -> Iterable[tuple[str, str]]:
    s = datetime.strptime(start_date, "%Y%m%d")
    e = datetime.strptime(end_date, "%Y%m%d")
    y = s.year
    while y <= e.year:
        ws = max(s, datetime(y, 1, 1))
        we = min(e, datetime(y, 12, 31))
        yield ws.strftime("%Y%m%d"), we.strftime("%Y%m%d")
        y += 1


class CodeRangeTaskBuilder:
    def __init__(self, *, window: str = "year"):
        self.window = window

    def build(self, _pro, spec: DatasetSpec, *, ts_codes: list[str], start_date: str, end_date: str) -> list[Task]:
        if spec.date_col is None:
            raise TaskBuildError(f"{spec.name}: ts_code_range 模式必须提供 date_col")
        tasks: list[Task] = []
        if self.window != "year":
            raise TaskBuildError(f"暂不支持 window={self.window}")
        for code in ts_codes:
            for sd, ed in _iter_year_windows(start_date, end_date):
                tasks.append(Task(spec=spec, request_params={"ts_code": code, "start_date": sd, "end_date": ed}))
        return tasks


class SnapshotTaskBuilder:
    def build(self, _pro, spec: DatasetSpec, *, params: dict | None = None) -> list[Task]:
        return [Task(spec=spec, request_params=dict(params or {}))]


class PeriodTaskBuilder:
    def build(self, _pro, spec: DatasetSpec, *, start: str, end: str) -> list[Task]:
        if spec.fetch_mode == "period_month":
            return [Task(spec=spec, request_params={"start_m": start, "end_m": end})]
        if spec.fetch_mode == "period_quarter":
            return [Task(spec=spec, request_params={"start_q": start, "end_q": end})]
        raise TaskBuildError(f"{spec.name}: 不支持的 period 模式: {spec.fetch_mode}")

