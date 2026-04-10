from __future__ import annotations

import argparse
import time
from pathlib import Path

from ts_download_utils import (
    compact_parquet_files_to_single,
    ensure_dir,
    list_files_recursive,
    safe_rmtree,
    atomic_replace,
)


def compact_generic(raw_dir: Path, name: str, *, suffix: str = "", delete_parts: bool = False) -> dict:
    # if name == "cyq_perf":
    #     return {"dataset": name, "skipped": True, "reason": "cyq_perf is already handled manually"}

    # 查找所有匹配 {name}_*parts 的目录
    parts_dirs = [d for d in raw_dir.iterdir() if d.is_dir() and d.name.startswith(f"{name}_") and d.name.endswith("_parts")]
    # 也要包含默认的 {name}_parts 目录
    default_parts = raw_dir / f"{name}_parts"
    if default_parts.exists() and default_parts.is_dir():
        parts_dirs.append(default_parts)
    
    parts_dirs = list(set(parts_dirs)) # 去重
    
    out_path = raw_dir / f"{name}{suffix}.parquet"
    
    # 收集所有碎片文件
    all_parts_files = []
    for d in parts_dirs:
        all_parts_files.extend(list_files_recursive(d, suffix=".parquet"))
    
    # 检查是否存在旧的主文件
    existing_files = []
    if out_path.exists():
        # 生成带时间戳的备份文件名
        bak_name = out_path.with_name(f"{out_path.name}.bak_{int(time.time())}")
        try:
            # 使用复制而不是重命名，增加一层安全性
            import shutil
            shutil.copy2(out_path, bak_name)
            existing_files.append(bak_name)
            print(f"!!! 已备份主文件至 {bak_name} 并加入合并队列 !!!")
        except Exception as e:
            print(f"!!! 备份失败 {out_path}: {e} !!!")
            return {"dataset": name, "status": "failed", "reason": f"Backup failed: {e}"}
    
    all_input_files = existing_files + all_parts_files
    
    if not all_input_files:
        return {"dataset": name, "skipped": True, "reason": "no files (neither new parts nor old file)"}
    
    print(f">>> 开始合并 {name}: 总计 {len(all_input_files)} 个输入文件...")
    
    try:
        # 执行合并 (内部已实现 float32 转换和批量读取优化)
        res = compact_parquet_files_to_single(all_input_files, out_path, downcast_floats=True)
    except Exception as e:
        print(f"!!! {name} 合并过程中发生致命错误: {e} !!!")
        raise e
    
    # 合并成功后，根据参数决定是否清理
    if delete_parts:
        print(f"--- 正在清理 {name} 的碎片目录 ---")
        for d in parts_dirs:
            safe_rmtree(d)
        # 只有在明确要求删除碎片时，才删除备份文件
        for f in existing_files:
            try:
                f.unlink()
            except Exception:
                pass
    else:
        print(f"--- [安全模式] 保留 {name} 的碎片目录和备份文件 ---")
            
    return {
        "dataset": name,
        "rows": res.rows,
        "out": res.path,
        "parts_files": len(all_parts_files),
        "parts_dirs_processed": len(parts_dirs),
        "old_files_merged": len(existing_files),
        "deleted_parts": bool(delete_parts)
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--raw-dir", default=r"d:\Trading\data_ever_26_3_14\data\Raw_data")
    p.add_argument("--datasets", default="moneyflow,daily_basic,daily,stk_limit,suspend_d") # 移除 cyq_perf 默认值
    # python src_data_download.compact_raw_data --datasets cyq_perf
    p.add_argument("--delete-parts", action="store_true", help="只有明确指定才会删除碎片目录")
    args = p.parse_args()

    raw_dir = Path(args.raw_dir)
    ensure_dir(raw_dir)
    datasets = [x.strip() for x in str(args.datasets).split(",") if x.strip()]
    delete_parts = bool(args.delete_parts)

    reports: list[dict] = []
    for name in datasets:
        reports.append(compact_generic(raw_dir, name, delete_parts=delete_parts))

    for r in reports:
        print(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
