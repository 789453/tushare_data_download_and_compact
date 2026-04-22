from __future__ import annotations

from ..core.dataset_spec import DatasetSpec

SPEC = DatasetSpec(
    name="index_daily_selected",
    api_name="index_daily",
    asset_class="index",
    fetch_mode="ts_code_range",
    pk_cols=("ts_code", "trade_date"),
    partition_cols=("ts_code", "start_date", "end_date"),
    date_col="trade_date",
    required_fields=("ts_code", "trade_date", "close"),
    limit=8000,
    supports_offset=True,
    supports_trade_cal=False,
    stable_before="20160301",
    lookback_days=30,
)

