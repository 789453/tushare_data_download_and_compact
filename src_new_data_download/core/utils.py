from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def canonical_json(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha1_text(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_replace(src: Path, dst: Path) -> None:
    ensure_dir(dst.parent)
    if dst.exists():
        dst.unlink()
    src.replace(dst)


def write_parquet_atomic(
    out_path: Path,
    df: "object",
    *,
    compression: str = "zstd",
) -> object:
    import pyarrow as pa
    import pyarrow.parquet as pq

    ensure_dir(out_path.parent)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(
        table,
        tmp,
        compression=compression,
        use_dictionary=True,
        write_statistics=True,
    )
    atomic_replace(tmp, out_path)
    
    # Return a simple object with rows and path to match old signature
    from dataclasses import dataclass
    @dataclass
    class Res:
        rows: int
        path: str
    return Res(rows=int(table.num_rows), path=str(out_path))


def today_yyyymmdd() -> str:
    return datetime.now().strftime("%Y%m%d")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def get_tushare_token() -> str:
    import os
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        # Try reading from a file if env var is missing
        token_file = Path.home() / ".tushare_token"
        if token_file.exists():
            return token_file.read_text(encoding="utf-8").strip()
        raise RuntimeError("环境变量 TUSHARE_TOKEN 为空，且未找到 ~/.tushare_token")
    return token


def load_tushare_pro(token: str | None = None):
    token = token or get_tushare_token()
    import tushare as ts
    return ts.pro_api(token)


def retry_call(
    fn,
    *,
    max_attempts: int = 8,
    base_sleep_s: float = 1.0,
    max_sleep_s: float = 30.0,
):
    import random
    import time
    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as e:
            last_err = e
            if attempt >= max_attempts:
                break
            sleep_s = min(max_sleep_s, base_sleep_s * (2 ** (attempt - 1)))
            sleep_s = sleep_s * (0.7 + random.random() * 0.6)
            time.sleep(sleep_s)
    raise RuntimeError(f"调用失败，已重试 {max_attempts} 次: {last_err}") from last_err


def paginated_fetch(
    pro,
    api_name: str,
    *,
    limit: int,
    params: dict,
):
    offset = 0
    api = getattr(pro, api_name)
    while True:
        def _call():
            return api(limit=limit, offset=offset, **params)

        df = retry_call(_call)
        if df is None or df.empty:
            break
        yield df
        got = int(getattr(df, "shape", (0, 0))[0])
        if got < limit:
            break
        offset += limit


def try_read_git_sha(project_root: Path) -> str | None:
    head = project_root / ".git" / "HEAD"
    if not head.exists():
        return None
    raw = head.read_text(encoding="utf-8").strip()
    if raw.startswith("ref:"):
        ref = raw.split(":", 1)[1].strip()
        ref_path = project_root / ".git" / ref
        if ref_path.exists():
            return ref_path.read_text(encoding="utf-8").strip()[:40] or None
        packed = project_root / ".git" / "packed-refs"
        if packed.exists():
            for line in packed.read_text(encoding="utf-8").splitlines():
                if not line or line.startswith("#") or line.startswith("^"):
                    continue
                parts = line.split()
                if len(parts) == 2 and parts[1].strip() == ref:
                    return parts[0].strip()[:40] or None
        return None
    return raw[:40] or None

