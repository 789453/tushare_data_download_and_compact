from __future__ import annotations

from ..core.utils import retry_call


def iter_trade_dates_yyyymmdd(pro, start_date: str, end_date: str) -> list[str]:
    def _call():
        return pro.trade_cal(
            exchange="",
            start_date=start_date,
            end_date=end_date,
            is_open="1",
            fields="cal_date",
        )

    df = retry_call(_call)
    if df is None or df.empty:
        return []
    dates = [str(x) for x in df["cal_date"].tolist()]
    dates = sorted(set(dates))
    return dates
