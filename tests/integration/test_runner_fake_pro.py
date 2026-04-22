from __future__ import annotations

from pathlib import Path

import pandas as pd

from src_data_download.core.dataset_spec import DatasetSpec
from src_data_download.core.runner import Runner
from src_data_download.core.task_builders import Task


class FakePro:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def index_daily(self, *, limit: int, offset: int, **params):
        self.calls.append(("index_daily", {"limit": limit, "offset": offset, **params}))
        if offset == 0:
            return pd.DataFrame(
                [
                    {"ts_code": params["ts_code"], "trade_date": "20240102", "close": 1.0},
                    {"ts_code": params["ts_code"], "trade_date": "20240103", "close": 2.0},
                ]
            )
        return pd.DataFrame()


def test_runner_writes_parquet_and_sidecar(tmp_path: Path):
    project_root = tmp_path / "proj"
    project_root.mkdir()
    raw_root = tmp_path / "raw"
    state_path = tmp_path / "state.json"

    runner = Runner(project_root=project_root, raw_root=raw_root, state_path=state_path)
    pro = FakePro()

    spec = DatasetSpec(
        name="index_daily",
        api_name="index_daily",
        asset_class="index",
        fetch_mode="ts_code_range",
        pk_cols=("ts_code", "trade_date"),
        partition_cols=("ts_code", "start_date", "end_date"),
        date_col="trade_date",
        required_fields=("ts_code", "trade_date", "close"),
        limit=8000,
    )
    t = Task(spec=spec, request_params={"ts_code": "000300.SH", "start_date": "20240101", "end_date": "20241231"})

    results = runner.run(pro=pro, tasks=[t], max_workers=1, overwrite=True)
    assert len(results) == 1
    r = results[0]
    assert r.status == "done"
    assert r.rows == 2
    assert r.parquet_path is not None

    parquet = Path(r.parquet_path)
    assert parquet.exists()
    assert parquet.with_suffix(parquet.suffix + ".meta.json").exists()

