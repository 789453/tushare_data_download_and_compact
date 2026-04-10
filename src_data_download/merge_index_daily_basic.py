import pandas as pd
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    raw_dir = Path(r"d:\Trading\data_ever_26_3_14\data\Raw_data")
    index_member_path = raw_dir / "index_member_all.parquet"
    daily_basic_path = raw_dir / "daily_basic.parquet"
    output_path = raw_dir / "index_daily_basic_circ_mv.parquet"

    logger.info("开始提取数据...")
    
    # Check if files exist
    if not index_member_path.exists():
        logger.error(f"文件不存在: {index_member_path}")
        return
    if not daily_basic_path.exists():
        logger.error(f"文件不存在: {daily_basic_path}")
        return

    # Only read necessary columns to save IO and memory
    try:
        logger.info(f"读取 {index_member_path.name} 的 l1_name 和 ts_code...")
        df_index = pd.read_parquet(index_member_path, columns=["l1_name", "ts_code"])
        
        # In case a stock belongs to multiple indices, we keep the mapping
        # but check for duplicates if necessary. 
        # Usually ts_code in index_member is unique if it's a direct mapping.
        
        logger.info(f"读取 {daily_basic_path.name} 的 ts_code, trade_date, circ_mv...")
        df_daily = pd.read_parquet(daily_basic_path, columns=["ts_code", "trade_date", "circ_mv"])
        
        logger.info("开始匹配关联 (Merge)...")
        # Perform inner join on ts_code
        # This will add l1_name to each daily record of that ts_code
        df_merged = df_daily.merge(df_index, on="ts_code", how="inner")
        
        # Rearrange columns as requested: l1_name, ts_code, trade_date, circ_mv
        df_merged = df_merged[["l1_name", "ts_code", "trade_date", "circ_mv"]]
        
        logger.info(f"关联完成，结果共 {len(df_merged)} 行。")
        
        logger.info(f"保存结果至 {output_path}...")
        df_merged.to_parquet(output_path, index=False, compression="zstd")
        
        logger.info("任务成功完成！")
        
    except Exception as e:
        logger.exception(f"合并过程中发生错误: {e}")

if __name__ == "__main__":
    main()
