from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .exceptions import SpecValidationError

AssetClass = Literal["stock", "index", "futures", "options", "macro", "fx"]
FetchMode = Literal["trade_date", "ts_code_range", "snapshot", "period_month", "period_quarter"]


@dataclass(frozen=True, slots=True)
class DatasetSpec:
    name: str
    api_name: str
    asset_class: AssetClass
    fetch_mode: FetchMode
    pk_cols: tuple[str, ...]
    partition_cols: tuple[str, ...]
    date_col: str | None
    required_fields: tuple[str, ...] = ()
    optional_fields: tuple[str, ...] = ()
    limit: int = 2000
    supports_offset: bool = True
    supports_trade_cal: bool = False
    exchange_filter: str | None = None
    market_filter: str | None = None
    timezone: str | None = None

    def validate(self) -> None:
        if not self.name or not self.name.strip():
            raise SpecValidationError("DatasetSpec.name 不能为空")
        if not self.api_name or not self.api_name.strip():
            raise SpecValidationError(f"{self.name}: api_name 不能为空")
        if not self.pk_cols:
            raise SpecValidationError(f"{self.name}: pk_cols 不能为空")
        if self.date_col is not None and not str(self.date_col).strip():
            raise SpecValidationError(f"{self.name}: date_col 非空时必须为有效字符串")
        if self.limit <= 0:
            raise SpecValidationError(f"{self.name}: limit 必须 > 0")
        if len(set(self.pk_cols)) != len(self.pk_cols):
            raise SpecValidationError(f"{self.name}: pk_cols 不允许重复")
        if len(set(self.partition_cols)) != len(self.partition_cols):
            raise SpecValidationError(f"{self.name}: partition_cols 不允许重复")
        if set(self.required_fields) & set(self.optional_fields):
            raise SpecValidationError(f"{self.name}: required_fields 与 optional_fields 不允许交集")

