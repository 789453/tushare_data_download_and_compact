from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TushareRuntime:
    token: str | None = None


def load_pro(*, token: str | None = None):
    from ..ts_download_utils import load_tushare_pro

    return load_tushare_pro(token=token)

