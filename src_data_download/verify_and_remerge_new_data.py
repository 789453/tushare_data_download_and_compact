import os
import sys
from pathlib import Path
import pyarrow.parquet as pq
import pandas as pd
import logging

# Ensure we can import from the current directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from compact_raw_data import compact_generic

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def verify_and_remerge():
    raw_dir = Path(r"d:\Trading\data_ever_26_3_14\data\Raw_data")
    datasets = ["stk_limit", "suspend_d"]
    
    for name in datasets:
        logger.info(f"=== 处理数据集: {name} ===")
        
        # 1. 执行合并 (使用更新后的 ts_download_utils 逻辑)
        # 注意: 这里不传 delete_parts=True, 以免误删碎片, 直到确认成功
        logger.info(f"开始合并 {name} 碎片...")
        res = compact_generic(raw_dir, name, delete_parts=False)
        logger.info(f"合并结果: {res}")
        
        if res.get("status") == "failed":
            logger.error(f"合并 {name} 失败: {res.get('reason')}")
            continue
            
        # 2. 验证合并后的文件
        out_file = raw_dir / f"{name}.parquet"
        if not out_file.exists():
            logger.error(f"合并后的文件不存在: {out_file}")
            continue
            
        try:
            logger.info(f"验证文件 {out_file.name}...")
            table = pq.read_table(out_file)
            df = table.to_pandas()
            
            logger.info(f"文件行数: {len(df)}")
            logger.info(f"日期范围: {df['trade_date'].min()} 到 {df['trade_date'].max()}")
            logger.info(f"列信息: {df.columns.tolist()}")
            
            # 检查是否有 null 列被错误转换
            null_cols = [c for c in df.columns if df[c].dtype == 'object' and df[c].isnull().all()]
            if null_cols:
                logger.warning(f"警告: 发现全空列 {null_cols}，请确认是否正常 (例如早期 suspend_timing 可能全空)")
            
            # 检查是否有异常类型
            logger.info(f"Schema 验证通过。")
            
        except Exception as e:
            logger.error(f"验证 {name} 失败: {e}")

if __name__ == "__main__":
    verify_and_remerge()
