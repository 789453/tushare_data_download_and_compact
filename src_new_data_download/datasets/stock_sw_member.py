from __future__ import annotations

from ..core.dataset_spec import DatasetSpec

SPEC = DatasetSpec(
    name="stock_sw_member",
    api_name="index_member",
    asset_class="stock",
    fetch_mode="ts_code_range",
    pk_cols=("index_code", "con_code", "in_date"),
    partition_cols=("index_code",),
    date_col="in_date",
    required_fields=("index_code", "con_code", "in_date"),
    limit=5000,
    supports_offset=True,
    supports_trade_cal=False,
    lookback_days=0,
)
