from __future__ import annotations

from ..core.dataset_spec import DatasetSpec

SPEC = DatasetSpec(
    name="sge_daily",
    api_name="sge_daily",
    asset_class="macro",
    fetch_mode="trade_date",
    pk_cols=("ts_code", "trade_date"),
    partition_cols=("trade_date",),
    date_col="trade_date",
    required_fields=("ts_code", "trade_date", "close"),
    limit=2000,
    supports_offset=True,
    supports_trade_cal=False,
)

