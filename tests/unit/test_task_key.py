from __future__ import annotations

from src_data_download.core.dataset_spec import DatasetSpec
from src_data_download.core.task_builders import Task


def test_task_key_stable_for_dict_order():
    spec = DatasetSpec(
        name="index_daily",
        api_name="index_daily",
        asset_class="index",
        fetch_mode="ts_code_range",
        pk_cols=("ts_code", "trade_date"),
        partition_cols=("ts_code", "start_date", "end_date"),
        date_col="trade_date",
    )
    t1 = Task(spec=spec, request_params={"ts_code": "000300.SH", "start_date": "20240101", "end_date": "20241231"})
    t2 = Task(spec=spec, request_params={"end_date": "20241231", "start_date": "20240101", "ts_code": "000300.SH"})
    assert t1.task_key == t2.task_key
    assert t1.params_hash == t2.params_hash

