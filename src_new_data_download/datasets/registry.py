from __future__ import annotations

from ..core.dataset_spec import DatasetSpec
from . import (
    stock_daily,
    stock_daily_basic,
    stock_moneyflow,
    index_basic,
    index_daily,
    index_dailybasic,
    cffex_fut_basic,
    cffex_fut_mapping,
    cffex_fut_daily,
    cffex_opt_basic,
    cffex_opt_daily,
    fx_basic,
    fx_daily,
    macro_gdp,
    macro_cpi,
    macro_ppi,
)

REGISTRY: dict[str, DatasetSpec] = {
    "stock_daily": stock_daily.SPEC,
    "stock_daily_basic": stock_daily_basic.SPEC,
    "stock_moneyflow": stock_moneyflow.SPEC,
    "index_basic_selected": index_basic.SPEC,
    "index_daily_selected": index_daily.SPEC,
    "index_dailybasic_supported": index_dailybasic.SPEC,
    "cffex_fut_basic": cffex_fut_basic.SPEC,
    "cffex_fut_mapping_selected": cffex_fut_mapping.SPEC,
    "cffex_fut_daily_selected": cffex_fut_daily.SPEC,
    "cffex_opt_basic_full": cffex_opt_basic.SPEC,
    "cffex_opt_daily": cffex_opt_daily.SPEC,
    "fx_basic_selected": fx_basic.SPEC,
    "fx_daily_selected": fx_daily.SPEC,
    "macro_cn_gdp": macro_gdp.SPEC,
    "macro_cn_cpi": macro_cpi.SPEC,
    "macro_cn_ppi": macro_ppi.SPEC,
}
