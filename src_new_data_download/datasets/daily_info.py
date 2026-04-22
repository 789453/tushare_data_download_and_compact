from __future__ import annotations

from ..core.dataset_spec import DatasetSpec

SPEC = DatasetSpec(
    name="daily_info",
    api_name="daily_info",
    asset_class="index",
    fetch_mode="trade_date",
    pk_cols=("trade_date", "exchange", "ts_code"),
    partition_cols=("trade_date", "exchange"),
    date_col="trade_date",
    required_fields=("trade_date", "exchange", "ts_code", "ts_name"),
    limit=4000,
    supports_offset=True,
    supports_trade_cal=True,
)

