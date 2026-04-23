from __future__ import annotations

from ..core.dataset_spec import DatasetSpec

SPEC = DatasetSpec(
    name="stock_basic_snapshot",
    api_name="stock_basic",
    asset_class="stock",
    fetch_mode="snapshot",
    pk_cols=("ts_code",),
    partition_cols=("snapshot_date",),
    date_col=None,
    required_fields=("ts_code", "symbol", "name", "area", "industry", "list_date"),
    limit=5000,
    supports_offset=True,
    supports_trade_cal=False,
    keep_snapshots=True,
)
