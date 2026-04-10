import polars as pl
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_file_duplicates(path: Path):
    if not path.exists():
        logger.warning(f"文件未找到: {path}")
        return None
    
    logger.info(f"检查文件: {path.name} ...")
    try:
        df = pl.read_parquet(path)
        total_rows = df.height
        
        # 1. 完全重复行 (All columns)
        total_duplicates = total_rows - df.unique().height
        
        # 2. 业务主键重复行 (ts_code + trade_date/trade_time)
        key_cols = []
        if 'ts_code' in df.columns:
            key_cols.append('ts_code')
        if 'trade_date' in df.columns:
            key_cols.append('trade_date')
        elif 'trade_time' in df.columns:
            key_cols.append('trade_time')
            
        key_duplicates = 0
        if len(key_cols) >= 2:
            key_duplicates = total_rows - df.unique(subset=key_cols).height
            
        return {
            "file": path.name,
            "total_rows": total_rows,
            "all_cols_dups": total_duplicates,
            "key_dups": key_duplicates,
            "key_cols": key_cols
        }
    except Exception as e:
        logger.error(f"处理 {path.name} 时出错: {e}")
        return None

def main():
    raw_dir = Path(r"d:\Trading\data_ever_26_3_14\data\Raw_data")
    domain_dir = Path(r"d:\Trading\data_ever_26_3_14\data\Feature_data\domain")
    
    raw_files = [
        raw_dir / "daily.parquet",
        raw_dir / "moneyflow.parquet",
        raw_dir / "cyq_perf.parquet",
        raw_dir / "stk_60_mins.parquet"
    ]
    
    domain_files = list(domain_dir.glob("*.parquet"))
    
    all_results = []
    
    logger.info("--- 检查 Raw 层数据 ---")
    for f in raw_files:
        res = check_file_duplicates(f)
        if res: all_results.append(res)
        
    logger.info("--- 检查 Domain 层数据 ---")
    for f in domain_files:
        res = check_file_duplicates(f)
        if res: all_results.append(res)
        
    # 打印总结表格
    print("\n" + "="*80)
    print(f"{'文件名':<35} | {'总行数':<12} | {'完全重复':<10} | {'主键重复':<10}")
    print("-" * 80)
    for res in all_results:
        print(f"{res['file']:<35} | {res['total_rows']:<12} | {res['all_cols_dups']:<10} | {res['key_dups']:<10}")
    print("="*80)

if __name__ == "__main__":
    main()
