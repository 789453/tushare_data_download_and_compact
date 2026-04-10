from __future__ import annotations

import json
import os
import random
import shutil
import time
import zlib
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Iterable, Iterator, Literal


class DownloadError(RuntimeError):
    pass


def yyyymmdd(d: date) -> str:
    return d.strftime("%Y%m%d")


def today_yyyymmdd() -> str:
    return yyyymmdd(date.today())


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def get_tushare_token() -> str:
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        raise DownloadError("环境变量 TUSHARE_TOKEN 为空")
    return token


def load_tushare_pro(token: str | None = None):
    token = token or get_tushare_token()
    import tushare as ts

    return ts.pro_api(token)


def retry_call(
    fn: Callable[[], "object"],
    *,
    max_attempts: int = 8,
    base_sleep_s: float = 1.0,
    max_sleep_s: float = 30.0,
) -> "object":
    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt >= max_attempts:
                break
            sleep_s = min(max_sleep_s, base_sleep_s * (2 ** (attempt - 1)))
            sleep_s = sleep_s * (0.7 + random.random() * 0.6)
            time.sleep(sleep_s)
    raise DownloadError(f"调用失败，已重试 {max_attempts} 次: {last_err}") from last_err


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


def iter_trade_dates_iso(pro, start_date: str, end_date: str) -> list[str]:
    dates = iter_trade_dates_yyyymmdd(pro, start_date, end_date)
    return [datetime.strptime(d, "%Y%m%d").strftime("%Y-%m-%d") for d in dates]


def paginated_fetch(
    pro,
    api_name: str,
    *,
    limit: int,
    params: dict,
) -> Iterator["object"]:
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


@dataclass(frozen=True)
class ParquetWriteResult:
    rows: int
    files: int
    path: str


def atomic_replace(src: Path, dst: Path) -> None:
    ensure_dir(dst.parent)
    if dst.exists():
        dst.unlink()
    src.replace(dst)


def write_parquet_atomic(
    out_path: Path,
    df: "object",
    *,
    compression: Literal["zstd", "snappy"] = "zstd",
) -> ParquetWriteResult:
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
    return ParquetWriteResult(rows=int(table.num_rows), files=1, path=str(out_path))


def write_parquet_stream(
    out_path: Path,
    frames: Iterable["object"],
    *,
    compression: Literal["zstd", "snappy"] = "zstd",
) -> ParquetWriteResult:
    import pyarrow as pa
    import pyarrow.parquet as pq

    writer: pq.ParquetWriter | None = None
    total_rows = 0
    files = 0
    try:
        for df in frames:
            if df is None or df.empty:
                continue
            table = pa.Table.from_pandas(df, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(
                    str(out_path),
                    table.schema,
                    compression=compression,
                    use_dictionary=True,
                    write_statistics=True,
                )
            writer.write_table(table)
            total_rows += int(table.num_rows)
        if writer is not None:
            writer.close()
            files = 1
    finally:
        if writer is not None:
            try:
                writer.close()
            except Exception:  # noqa: BLE001
                pass
    return ParquetWriteResult(rows=total_rows, files=files, path=str(out_path))


def read_stock_basic_codes(stock_basic_parquet: Path) -> tuple[list[str], dict[str, str | None]]:
    import pandas as pd

    df = pd.read_parquet(stock_basic_parquet)
    if "ts_code" not in df.columns:
        raise DownloadError(f"stock_basic 缺少 ts_code 列: {stock_basic_parquet}")
    codes = [str(x) for x in df["ts_code"].dropna().unique().tolist()]
    list_date_by_code: dict[str, str | None] = {}
    if "list_date" in df.columns:
        tmp = df[["ts_code", "list_date"]].dropna(subset=["ts_code"])
        for _, row in tmp.iterrows():
            code = str(row["ts_code"])
            v = row.get("list_date", None)
            if v is None:
                list_date_by_code[code] = None
            else:
                s = str(v)
                list_date_by_code[code] = s if s and s != "nan" else None
    return codes, list_date_by_code


def save_json(path: Path, obj: object) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path) -> object | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


class StateManifest:
    """
    统一的状态管理器，避免产生数千个碎片 JSON。
    使用一个大 JSON 文件记录所有子任务的状态。
    """

    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, bool] = {}
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                self.data = {}

    def is_done(self, key: str) -> bool:
        return self.data.get(str(key), False)

    def mark_done(self, key: str):
        self.data[str(key)] = True
        self.save()

    def save(self):
        ensure_dir(self.path.parent)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")


def get_parquet_max_date(path: Path, date_col: str = "trade_date") -> str | None:
    """
    高效获取 Parquet 文件中最大的日期。
    """
    import pandas as pd
    import pyarrow.parquet as pq

    if not path.exists():
        return None
    try:
        pf = pq.ParquetFile(path)
        if pf.metadata.num_rows == 0:
            return None
        
        # 优化: 优先尝试从元数据统计信息中获取，避免读取全表
        try:
            max_val = None
            for i in range(pf.metadata.num_row_groups):
                # 找到日期列的索引
                col_idx = -1
                for j in range(pf.metadata.num_columns):
                    if pf.metadata.row_group(i).column(j).path_in_schema == date_col:
                        col_idx = j
                        break
                
                if col_idx != -1:
                    stats = pf.metadata.row_group(i).column(col_idx).statistics
                    if stats and stats.has_max:
                        curr_max = stats.max
                        if max_val is None or curr_max > max_val:
                            max_val = curr_max
            
            if max_val is not None:
                val = str(max_val).replace("-", "")
                return val
        except Exception: # 统计信息读取失败，降级到全列读取
            pass

        # 降级方案: 只读取日期列
        df = pd.read_parquet(path, columns=[date_col])
        if df.empty:
            return None
        val = df[date_col].astype(str).max()
        if "-" in val:
            val = val.replace("-", "")
        return val
    except Exception as e:
        print(f"Error reading max date from {path}: {e}")
        return None


def list_files_recursive(root: Path, suffix: str = ".parquet") -> list[Path]:
    if not root.exists():
        return []
    return sorted([p for p in root.rglob(f"*{suffix}") if p.is_file()])


def compact_parquet_files_to_single(
    parquet_files: list[Path],
    out_path: Path,
    *,
    compression: Literal["zstd", "snappy"] = "zstd",
    downcast_floats: bool = True,
    deduplicate: bool = True,
) -> ParquetWriteResult:
    import pyarrow as pa
    import pyarrow.parquet as pq

    if not parquet_files:
        raise DownloadError("没有可合并的 parquet 文件")

    ensure_dir(out_path.parent)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()

    writer: pq.ParquetWriter | None = None
    total_rows = 0
    target_schema = None

    # 性能优化策略：批量读取小文件，合并后再写入
    files_per_batch = 200 
    
    # 定义去重的主键列名
    pk_cols = ["ts_code", "trade_date"] # 默认
    
    try:
        for i in range(0, len(parquet_files), files_per_batch):
            batch_files = parquet_files[i : i + files_per_batch]
            tables = []
            
            for fp in batch_files:
                try:
                    table = pq.read_table(fp)
                    if table.num_rows == 0:
                        continue
                    
                    # 初始化 target_schema (使用前几个有数据的表的结构来综合确定最佳类型)
                    if target_schema is None:
                        # 尝试通过前几个文件探测更准确的 Schema（特别是处理 suspend_timing 等可能全 null 的列）
                        probe_count = min(len(batch_files), 100)
                        temp_schemas = []
                        for probe_fp in batch_files[:probe_count]:
                            try:
                                temp_schemas.append(pq.read_schema(probe_fp))
                            except Exception:
                                pass
                        
                        if not temp_schemas:
                            target_schema = table.schema
                        else:
                            # 合并 Schema: 如果同一个列在不同文件里有不同类型（特别是 null vs string），取更具体的那个
                            base_schema = temp_schemas[0]
                            final_fields = list(base_schema)
                            
                            for other_schema in temp_schemas[1:]:
                                for i, other_field in enumerate(other_schema):
                                    if i < len(final_fields) and final_fields[i].name == other_field.name:
                                        # 如果当前是 null，但另一个 schema 有具体类型，则升级
                                        if final_fields[i].type == pa.null() and other_field.type != pa.null():
                                            final_fields[i] = other_field
                            
                            target_schema = pa.schema(final_fields)
                        
                        # 确定实际的主键列名（某些表用 trade_time）
                        if "trade_time" in target_schema.names:
                            pk_cols = ["ts_code", "trade_time"]
                        
                        # 如果需要降级 float64 -> float32 以节省空间
                        if downcast_floats:
                            new_fields = []
                            for field in target_schema:
                                # 对所有数值列（float64, int64, int32）统一转为 float32
                                if field.type in (pa.float64(), pa.int64(), pa.int32()):
                                    new_fields.append(pa.field(field.name, pa.float32(), nullable=field.nullable))
                                # 强制将 null 类型转为 string 类型，避免后续合并失败
                                elif field.type == pa.null():
                                    new_fields.append(pa.field(field.name, pa.string(), nullable=True))
                                else:
                                    new_fields.append(field)
                            target_schema = pa.schema(new_fields)
                    
                    # 对齐 Schema
                    if not table.schema.equals(target_schema):
                        new_columns = []
                        for field in target_schema:
                            if field.name in table.column_names:
                                col = table.column(field.name)
                                if not col.type.equals(field.type):
                                    try:
                                        # 使用 safe=False 允许在转换 float32 时发生微小的精度损失
                                        col = pa.compute.cast(col, field.type, safe=False)
                                    except Exception:
                                        # 降级方案：先转为 float64 再转为 float32，这在某些版本下更稳定
                                        if field.type == pa.float32():
                                            col = pa.compute.cast(col, pa.float64(), safe=False)
                                            col = pa.compute.cast(col, pa.float32(), safe=False)
                                        else:
                                            raise
                                new_columns.append(col)
                            else:
                                new_columns.append(pa.array([None] * table.num_rows, type=field.type))
                        table = pa.Table.from_arrays(new_columns, schema=target_schema)
                    
                    tables.append(table)
                except Exception as e:
                    print(f"!!! 警告: 读取文件失败 {fp}: {e}，跳过此文件 !!!")

            if not tables:
                continue

            # 合并当前批次的表
            merged_batch_table = pa.concat_tables(tables)
            
            # 在写入每个 Batch 之前，如果在 Batch 内部有重复，可以先去重一次（缓解整体压力）
            if deduplicate and len(tables) > 1:
                import pandas as pd
                df_batch = merged_batch_table.to_pandas()
                df_batch = df_batch.drop_duplicates(subset=pk_cols)
                merged_batch_table = pa.Table.from_pandas(df_batch, schema=target_schema)

            if writer is None:
                writer = pq.ParquetWriter(
                    str(tmp),
                    target_schema,
                    compression=compression,
                    use_dictionary=True,
                    write_statistics=True,
                    version="2.6", # 使用较新版本支持更好的统计
                )
            
            writer.write_table(merged_batch_table)
            total_rows += int(merged_batch_table.num_rows)
            print(f"  已合并 {min(i + files_per_batch, len(parquet_files))}/{len(parquet_files)} 文件...")

        if writer is not None:
            writer.close()
            writer = None
        
        # 最终去重：如果合并后的文件包含不同 Batch 间的重复，需要进行最终去重
        if deduplicate and tmp.exists():
            print(f">>> 开始对最终文件进行全局去重: {out_path.name}...")
            import pandas as pd
            # 使用 pandas 进行全量去重
            df_final = pd.read_parquet(tmp)
            df_final = df_final.drop_duplicates(subset=pk_cols, keep='first')
            df_final.to_parquet(out_path, index=False, compression=compression)
            
            # 重新获取去重后的总行数
            total_rows = int(pq.ParquetFile(out_path).metadata.num_rows)
            print(f"  全局去重完成，最终行数: {total_rows}")
            
            if tmp.exists():
                tmp.unlink()
        elif tmp.exists():
            atomic_replace(tmp, out_path)
        else:
            raise DownloadError("未能生成任何输出数据")

    finally:
        if writer is not None:
            try:
                writer.close()
            except Exception:  # noqa: BLE001
                pass
        if tmp.exists():
            try:
                tmp.unlink()
            except Exception:  # noqa: BLE001
                pass

    return ParquetWriteResult(rows=total_rows, files=1, path=str(out_path))


def safe_rmtree(path: Path) -> None:
    if not path.exists():
        return
    shutil.rmtree(path)


def stable_hash32(s: str) -> int:
    return int(zlib.adler32(s.encode("utf-8")) & 0xFFFFFFFF)


@dataclass
class Progress:
    total: int
    label: str
    start_ts: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.start_ts = time.time()
        self.done = 0
        self.rows = 0

    def update(self, *, done_inc: int = 1, rows_inc: int = 0, msg: str | None = None) -> None:
        self.done += done_inc
        self.rows += rows_inc
        elapsed = max(0.001, time.time() - self.start_ts)
        rate = self.rows / elapsed if self.rows else (self.done / elapsed)
        if msg:
            print(f"[{self.label}] {msg}")
        print(f"[{self.label}] {self.done}/{self.total} rows={self.rows} rate={rate:.2f}/s elapsed={elapsed:.1f}s")

