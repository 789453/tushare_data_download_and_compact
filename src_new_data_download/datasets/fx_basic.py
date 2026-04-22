from __future__ import annotations

from ..core.dataset_spec import DatasetSpec

SPEC = DatasetSpec(
    name="fx_basic_selected",
    api_name="fx_obasic",
    asset_class="fx",
    fetch_mode="snapshot",
    pk_cols=("ts_code",),
    partition_cols=("snapshot_date",),
    date_col=None,
    required_fields=("ts_code", "classify", "name"),
    limit=5000,
    supports_offset=True,
    supports_trade_cal=False,
    keep_snapshots=True,
)

