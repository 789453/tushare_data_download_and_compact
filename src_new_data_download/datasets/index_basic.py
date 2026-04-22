from __future__ import annotations

from ..core.dataset_spec import DatasetSpec

SPEC = DatasetSpec(
    name="index_basic",
    api_name="index_basic",
    asset_class="index",
    fetch_mode="snapshot",
    pk_cols=("ts_code",),
    partition_cols=("snapshot_date",),
    date_col=None,
    required_fields=("ts_code", "name", "market"),
    limit=5000,
    supports_offset=True,
    supports_trade_cal=False,
)

