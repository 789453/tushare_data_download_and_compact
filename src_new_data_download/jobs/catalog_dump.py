from __future__ import annotations

import argparse
from pathlib import Path

from ..adapters.tushare_client import load_pro
from ..core.sinks import ParquetSink
from ..jobs.config_loader import load_runtime_config, load_storage_config


def _fetch_all(pro, api_name: str, *, limit: int, params: dict):
    from ..ts_download_utils import paginated_fetch

    import pandas as pd

    frames = list(paginated_fetch(pro, api_name, limit=limit, params=params))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]
    storage = load_storage_config(project_root)
    runtime = load_runtime_config(project_root)

    p = argparse.ArgumentParser()
    p.add_argument("--catalog-root", default=str(storage.catalog_root))
    p.add_argument("--compression", default=str(runtime.compression))
    args = p.parse_args()

    catalog_root = Path(args.catalog_root)
    catalog_root.mkdir(parents=True, exist_ok=True)

    pro = load_pro()
    sink = ParquetSink(project_root=project_root, compression=str(args.compression))

    index_basic = _fetch_all(pro, "index_basic", limit=5000, params={})
    sink.write(
        catalog_root / "index_basic_full.parquet",
        index_basic,
        dataset="catalog_index_basic_full",
        api_name="index_basic",
        task_key="catalog_index_basic_full",
        request_params={},
    )

    fut_basic = _fetch_all(pro, "fut_basic", limit=2000, params={"exchange": "CFFEX"})
    sink.write(
        catalog_root / "fut_basic_cffex.parquet",
        fut_basic,
        dataset="catalog_fut_basic_cffex",
        api_name="fut_basic",
        task_key="catalog_fut_basic_cffex",
        request_params={"exchange": "CFFEX"},
    )

    opt_basic = _fetch_all(pro, "opt_basic", limit=2000, params={"exchange": "CFFEX"})
    sink.write(
        catalog_root / "opt_basic_cffex.parquet",
        opt_basic,
        dataset="catalog_opt_basic_cffex",
        api_name="opt_basic",
        task_key="catalog_opt_basic_cffex",
        request_params={"exchange": "CFFEX"},
    )

    fx_basic = _fetch_all(pro, "fx_obasic", limit=5000, params={})
    sink.write(
        catalog_root / "fx_obasic_full.parquet",
        fx_basic,
        dataset="catalog_fx_obasic_full",
        api_name="fx_obasic",
        task_key="catalog_fx_obasic_full",
        request_params={},
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

