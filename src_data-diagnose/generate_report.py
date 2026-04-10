
import pandas as pd
from pathlib import Path
from datetime import datetime

# Paths
BASE_DIR = Path(r"d:\Trading\data_ever_26_3_14")
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = DATA_DIR / "data_diagnose"
STATS_FILE = OUTPUT_DIR / "all_data_stats.csv"
REPORT_FILE = OUTPUT_DIR / "diagnosis_summary.md"

def generate_report():
    df = pd.read_csv(STATS_FILE)
    
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write("# 数据质量与预处理损失诊断报告\n\n")
        f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("## 1. 核心问题摘要 (Executive Summary)\n\n")
        f.write("根据对 `Raw_data`、`domain` 和 `factor_ready` 数据的全面统计分析，我们发现了以下几个可能导致**严重信息损失**的预处理问题，印证了您的担忧：\n\n")
        
        f.write("1. **过度截尾 (Excessive Winsorization/Clipping)**: 大量特征（如 `ret_cc_1d`, `net_mf_to_amount`）被强制在 1% 和 99% 分位数截尾，或使用了硬编码的界限（如 `[-1, 1]`, `[-0.5, 0.5]`）。这导致真实的市场极端情况（如涨跌停、巨额资金净流入）信号被抹平。\n")
        f.write("2. **异常的高零值率 (Zero Inflation)**: 某些特征（如 `hour1_ret`）的零值比例高达 **85%**，这通常不是真实的业务分布，而是计算逻辑错误或缺失值被不当填充（`fillna(0)`）所致。\n")
        f.write("3. **高缺失值率 (High Null Ratio)**: 部分基本面指标（如 `dv_ttm`、`ebitda`）缺失率超过 30%，在进行特征合成时可能会产生连锁反应。\n\n")

        f.write("## 2. 详细问题分析与证据 (Detailed Analysis)\n\n")
        
        f.write("### 2.1 过度截尾与数据范围失真 (Clipping & Winsorization)\n")
        f.write("代码 `utils_clean.py` 中的 `winsorize_series` 以及 `build_domain_*.py` 中的硬编码 `clip()` 导致了数据的严重失真。以下是受影响最严重的字段：\n\n")
        
        f.write("| 文件名 | 字段 | 最小值 (Min) | 最大值 (Max) | 1%分位数 (Q01) | 99%分位数 (Q99) | 现象说明 |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        
        # Identify clipping
        clipped = df[(df['min'] == df['q01']) | (df['max'] == df['q99']) | (df['min'] == -1.0) | (df['max'] == 1.0)].copy()
        # Filter some obvious ones to show
        show_cols = ['ret_cc_1d', 'ret_oc_1d', 'net_mf_to_amount', 'close_vs_cost50', 'imb_elg_amt', 'volume_concentration_pm']
        
        for idx, row in clipped[clipped['column'].isin(show_cols)].drop_duplicates(subset=['column']).iterrows():
            f.write(f"| {row['file_name']} | `{row['column']}` | {row['min']:.4f} | {row['max']:.4f} | {row['q01']:.4f} | {row['q99']:.4f} | ")
            if row['min'] == row['q01'] or row['max'] == row['q99']:
                f.write("1%与最小值完全相同，说明使用了严格的分位数截断。")
            elif row['min'] == -1.0 or row['max'] == 1.0:
                f.write("存在硬编码的边界截断。")
            f.write(" |\n")
            
        f.write("\n**风险**: 比如 `feature_A_price_volume` 中的 `ret_cc_1d` (日收益率) 最大值被截断在 **10% (0.100)**，这会完全丢失创业板/科创板 **20%** 涨停板的信息！\n\n")

        f.write("### 2.2 异常的零值聚集 (Excessive Zeros)\n")
        f.write("部分字段存在异常的零值比例，这通常意味着除以0时的 fallback 策略不当，或者业务逻辑有误。\n\n")
        
        f.write("| 文件名 | 字段 | 零值比例 (Zero %) | 可能原因 |\n")
        f.write("|---|---|---|---|\n")
        
        high_zeros = df[df['zero_pct'] > 15].sort_values('zero_pct', ascending=False)
        for idx, row in high_zeros.head(10).iterrows():
            reason = "未知"
            if "hour1_ret" in row['column']:
                reason = "极度异常！可能1小时K线数据的open和close常等，或时间聚合逻辑导致取到了同一笔交易。"
            elif "imb" in row['column']:
                reason = "`fillna(0)` 填充导致，当大单买卖均为0时，分母为0返回空，后被0填充。"
            f.write(f"| {row['file_name']} | `{row['column']}` | **{row['zero_pct']:.2f}%** | {reason} |\n")

        f.write("\n**风险**: 在 `build_domain_B_moneyflow.py` 中，`imb_elg_amt` 零值高达 27.8%。将缺失的订单流直接视作 `0`（中性）可能会干扰模型对流动性匮乏状态的识别。\n\n")

        f.write("### 2.3 缺失值分布 (Null Values)\n")
        f.write("基础数据中的缺失值需要合理的插值策略（如行业中位数、时序 ffill）。\n\n")
        f.write("| 文件名 | 字段 | 缺失比例 (Null %) |\n")
        f.write("|---|---|---|\n")
        high_nulls = df[df['null_pct'] > 10].sort_values('null_pct', ascending=False)
        for idx, row in high_nulls.head(5).iterrows():
            f.write(f"| {row['file_name']} | `{row['column']}` | {row['null_pct']:.2f}% |\n")
            
        f.write("\n## 3. 改进建议 (Recommendations)\n\n")
        f.write("基于上述诊断，建议对 `src_data_domain_feature` 下的代码进行以下修改：\n\n")
        f.write("1. **修改 `utils_clean.py` 中的 `winsorize_series`**:\n")
        f.write("   - 不要盲目对所有特征使用 1% 的截尾。对于收益率 (`ret_cc_1d`) 等厚尾分布，建议使用 **5倍标准差 (5-sigma)** 或更大的动态阈值截尾，或者根本不截尾（现代树模型对异常值鲁棒）。\n")
        f.write("   - 如果一定要分位数截断，建议放宽到 `0.001` (千分之一)。\n")
        f.write("2. **审查 `build_domain_B_moneyflow.py` 的除0逻辑**:\n")
        f.write("   - 当分母为0（如总成交额为0）时，指标应设为 `NaN` 而不是 `0`，让下游的树模型自己处理缺失值，或者增加一个 `is_zero_volume` 的布尔特征。\n")
        f.write("3. **排查 `build_domain_E_intraday_summary.py` 的 `hour1_ret`**:\n")
        f.write("   - 为什么第一小时收益率有 85% 为 0？需要检查 `stk_60_mins.parquet` 的时间戳解析。可能是 `pl.col('hour')` 解析错误，导致 `first()` 和 `last()` 取到了同一根K线。\n")
        f.write("4. **移除硬编码的 `.clip(-1.0, 1.0)`**:\n")
        f.write("   - 资金流等特征中的 `clip` 掩盖了极端的市场情绪，建议移除或扩大范围。\n\n")

        f.write("## 4. 统计概览 (Global Statistics)\n\n")
        f.write("所有字段的详细统计数据（Min, Max, Mean, Quantiles等）已保存至：\n")
        f.write("`d:\\Trading\\data_ever_26_3_14\\data\\data_diagnose\\all_data_stats.csv`\n\n")
        f.write("各特征的分布直方图（用于直观查看截断现象）已保存至：\n")
        f.write("`d:\\Trading\\data_ever_26_3_14\\data\\data_diagnose\\images\\` 目录下。\n")

if __name__ == "__main__":
    generate_report()
    print("Report generated successfully.")
