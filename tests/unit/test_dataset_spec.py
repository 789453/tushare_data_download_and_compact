from __future__ import annotations

import pytest

from src_data_download.core.dataset_spec import DatasetSpec
from src_data_download.core.exceptions import SpecValidationError


def test_dataset_spec_validate_ok():
    s = DatasetSpec(
        name="x",
        api_name="api",
        asset_class="stock",
        fetch_mode="trade_date",
        pk_cols=("ts_code", "trade_date"),
        partition_cols=("trade_date",),
        date_col="trade_date",
        required_fields=("ts_code", "trade_date"),
        limit=1,
        supports_offset=True,
        supports_trade_cal=True,
    )
    s.validate()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": "", "api_name": "api"},
        {"name": "x", "api_name": ""},
        {"name": "x", "api_name": "api", "pk_cols": ()},
        {"name": "x", "api_name": "api", "pk_cols": ("a",), "limit": 0},
    ],
)
def test_dataset_spec_validate_bad(kwargs):
    base = dict(
        name="x",
        api_name="api",
        asset_class="stock",
        fetch_mode="trade_date",
        pk_cols=("ts_code", "trade_date"),
        partition_cols=("trade_date",),
        date_col="trade_date",
        required_fields=("ts_code", "trade_date"),
        limit=1,
    )
    base.update(kwargs)
    s = DatasetSpec(**base)
    with pytest.raises(SpecValidationError):
        s.validate()

