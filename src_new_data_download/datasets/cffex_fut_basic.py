from __future__ import annotations

from ..core.dataset_spec import DatasetSpec

SPEC = DatasetSpec(
    name="cffex_fut_basic",
    api_name="fut_basic",
    asset_class="futures",
    fetch_mode="snapshot",
    pk_cols=("ts_code",),
    partition_cols=("snapshot_date",),
    date_col=None,
    required_fields=("ts_code", "symbol", "exchange", "name", "list_date"),
    limit=2000,
    supports_offset=True,
    supports_trade_cal=False,
    exchange_filter="CFFEX",
    keep_snapshots=True,
)

