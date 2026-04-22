from __future__ import annotations

from ..core.dataset_spec import DatasetSpec

SPEC = DatasetSpec(
    name="stock_moneyflow",
    api_name="moneyflow",
    asset_class="stock",
    fetch_mode="trade_date",
    pk_cols=("ts_code", "trade_date"),
    partition_cols=("trade_date",),
    date_col="trade_date",
    required_fields=("ts_code", "trade_date"),
    limit=6000,
    supports_offset=True,
    supports_trade_cal=True,
    stable_before="20160301",
    lookback_days=30,
)

