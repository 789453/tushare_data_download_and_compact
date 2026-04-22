from __future__ import annotations

from ..core.dataset_spec import DatasetSpec

SPEC = DatasetSpec(
    name="sge_basic",
    api_name="sge_basic",
    asset_class="macro",
    fetch_mode="snapshot",
    pk_cols=("ts_code",),
    partition_cols=("snapshot_date",),
    date_col=None,
    required_fields=("ts_code", "ts_name", "list_date"),
    limit=100,
    supports_offset=False,
    supports_trade_cal=False,
)



