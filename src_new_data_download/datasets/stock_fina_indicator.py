from __future__ import annotations

from ..core.dataset_spec import DatasetSpec

SPEC = DatasetSpec(
    name="stock_fina_indicator",
    api_name="fina_indicator_vip",
    asset_class="stock",
    fetch_mode="period_quarter",
    pk_cols=("ts_code", "end_date", "ann_date"),
    partition_cols=("end_date",),
    date_col="end_date",
    required_fields=("ts_code", "end_date", "ann_date"),
    limit=10000,
    supports_offset=False,
    supports_trade_cal=False,
    lookback_quarters=8,
)
