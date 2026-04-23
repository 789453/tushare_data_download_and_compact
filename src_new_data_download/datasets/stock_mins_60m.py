from __future__ import annotations

from ..core.dataset_spec import DatasetSpec

SPEC = DatasetSpec(
    name="stock_mins_60m",
    api_name="stk_mins",
    asset_class="stock",
    fetch_mode="ts_code_range",
    pk_cols=("ts_code", "trade_time"),
    partition_cols=("ts_code", "start_date", "end_date"),
    date_col="trade_time",
    required_fields=("ts_code", "trade_time", "close"),
    limit=8000,
    supports_offset=True,
    supports_trade_cal=False,
    extra_params={"freq": "60min"},
    lookback_days=10,
)
