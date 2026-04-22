from __future__ import annotations

from ..core.dataset_spec import DatasetSpec

SPEC = DatasetSpec(
    name="fx_daily",
    api_name="fx_daily",
    asset_class="fx",
    fetch_mode="ts_code_range",
    pk_cols=("ts_code", "trade_date"),
    partition_cols=("ts_code", "start_date", "end_date"),
    date_col="trade_date",
    required_fields=("ts_code", "trade_date", "bid_close", "ask_close"),
    limit=2000,
    supports_offset=True,
    supports_trade_cal=False,
    timezone="GMT",
)

