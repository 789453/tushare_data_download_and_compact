from __future__ import annotations

from ..core.dataset_spec import DatasetSpec

SPEC = DatasetSpec(
    name="cffex_opt_daily",
    api_name="opt_daily",
    asset_class="options",
    fetch_mode="ts_code_range",
    pk_cols=("ts_code", "trade_date"),
    partition_cols=("ts_code", "start_date", "end_date"),
    date_col="trade_date",
    required_fields=("ts_code", "trade_date", "close", "settle", "oi"),
    limit=15000,
    supports_offset=True,
    supports_trade_cal=False,
    exchange_filter="CFFEX",
)

