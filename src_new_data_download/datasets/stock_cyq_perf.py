from __future__ import annotations

from ..core.dataset_spec import DatasetSpec

SPEC = DatasetSpec(
    name="stock_cyq_perf",
    api_name="cyq_perf",
    asset_class="stock",
    fetch_mode="ts_code_range",
    pk_cols=("ts_code", "trade_date"),
    partition_cols=("ts_code", "start_date", "end_date"),
    date_col="trade_date",
    required_fields=("ts_code", "trade_date", "his_low", "his_high"),
    limit=5000,
    supports_offset=True,
    supports_trade_cal=False,
    lookback_days=30,
)
