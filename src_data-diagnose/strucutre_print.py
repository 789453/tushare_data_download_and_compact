import os
import json
from pathlib import Path

def scan_py_files(directory):
    """
    扫描目录下所有.py文件，自动忽略常见缓存、虚拟环境、IDE、数据、日志等文件/目录
    忽略规则完全匹配指定的忽略列表
    """
    # ===================== 忽略规则（完全按你提供的列表） =====================
    IGNORE_DIRS = {
        # Python cache
        "__pycache__",
        # Virtual environment
        ".venv", "venv", "env",
        # Jupyter
        ".ipynb_checkpoints",
        # IDE
        ".vscode", ".idea",".git",
        # Data / Results / Models
        "data", "results", "outputs", "plots",
    }

    IGNORE_EXTENSIONS = {
        ".pyc", ".pyo", ".pyd",
        ".log", ".pkl", ".joblib", ".h5", ".parquet"
    }

    IGNORE_FILES = {
        ".DS_Store", "Thumbs.db",
        ".env", "secrets.yaml", "config_local.yaml"
    }

    # 只扫描 .py 文件
    TARGET_EXT = ".py"
    py_files = []

    # 遍历目录
    for root, dirs, files in os.walk(directory):
        # ===== 1. 过滤需要忽略的文件夹（直接从遍历列表中移除，不再进入）=====
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

        # ===== 2. 处理当前目录下的文件 =====
        for file in files:
            file_path = Path(root) / file
            relative_path = file_path.relative_to(directory)
            posix_path = relative_path.as_posix()  # 统一用 / 分隔

            # # 只保留 .py 文件
            # if file_path.suffix != TARGET_EXT:
            #     continue

            # 忽略指定文件
            if file in IGNORE_FILES:
                continue

            # 忽略指定后缀
            if file_path.suffix in IGNORE_EXTENSIONS:
                continue

            # 符合条件：加入列表
            py_files.append(posix_path)

    # 排序并返回
    return {"_files": sorted(py_files)}


if __name__ == "__main__":
    # 扫描目标目录
    target_dir = r"D:\Trading\data_ever_26_3_14"
    result = scan_py_files(target_dir)

    # 保存 JSON
    output_file = "project_files.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"✅ 扫描完成！共找到 {len(result['_files'])} 个 .py 文件")
    print(f"📄 结果已保存到：{output_file}")