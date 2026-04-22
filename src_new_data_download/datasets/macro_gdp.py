from __future__ import annotations

from ..core.dataset_spec import DatasetSpec

SPEC = DatasetSpec(
    name="macro_gdp",
    api_name="cn_gdp",
    asset_class="macro",
    fetch_mode="period_quarter",
    pk_cols=("quarter",),
    partition_cols=("snapshot_date",),
    date_col="quarter",
    required_fields=("quarter", "gdp", "gdp_yoy"),
    limit=10000,
    supports_offset=False,
    supports_trade_cal=False,
)

