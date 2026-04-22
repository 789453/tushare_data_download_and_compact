from __future__ import annotations

from ..core.dataset_spec import DatasetSpec

SPEC = DatasetSpec(
    name="macro_money_supply",
    api_name="cn_m",
    asset_class="macro",
    fetch_mode="period_month",
    pk_cols=("month",),
    partition_cols=("snapshot_date",),
    date_col="month",
    required_fields=("month",),
    limit=10000,
    supports_offset=False,
    supports_trade_cal=False,
)

