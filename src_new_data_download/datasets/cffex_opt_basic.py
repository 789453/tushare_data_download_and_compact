from __future__ import annotations

from ..core.dataset_spec import DatasetSpec

SPEC = DatasetSpec(
    name="cffex_opt_basic",
    api_name="opt_basic",
    asset_class="options",
    fetch_mode="snapshot",
    pk_cols=("ts_code",),
    partition_cols=("snapshot_date",),
    date_col=None,
    required_fields=("ts_code", "call_put", "exercise_price", "maturity_date", "list_date", "delist_date"),
    limit=2000,
    supports_offset=True,
    supports_trade_cal=False,
    exchange_filter="CFFEX",
)

