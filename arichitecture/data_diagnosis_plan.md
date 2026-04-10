# Data Diagnosis and Analysis Plan

## 1. Objectives
The primary objective is to build a robust data diagnosis and analysis system to evaluate the quality, integrity, and distribution of trading data across different processing stages (Raw, Domain, Feature). This system will help identify potential data loss, excessive clipping, and anomalies introduced during preprocessing.

## 2. Scope
- **Input Data Sources**:
    - **Raw Data**: `d:\Trading\data_ever_26_3_14\data\Raw_data\*.parquet` (Level 1 only, excluding subdirectories).
    - **Feature Ready**: `d:\Trading\data_ever_26_3_14\data\Feature_data\factor_ready\*.parquet`.
    - **Domain Data**: `d:\Trading\data_ever_26_3_14\data\Feature_data\domain\*.parquet`.
- **Output**:
    - **Reports & Charts**: `d:\Trading\data_ever_26_3_14\data\data_diagnose`.
    - **Code**: `d:\Trading\data_ever_26_3_14\src_data-diagnose`.
- **Environment**:
    - OS: Windows (PowerShell).
    - Python: 3.11.
    - Libraries: `polars` (core), `pyarrow`, `plotly`/`matplotlib` (visualization), `pandas` (compatibility).
    - Environment Manager: Conda (`universal` env).

## 3. Architecture & Methodology

### 3.1. Directory Structure
```
d:\Trading\data_ever_26_3_14\
├── src_data-diagnose\           # Source code for diagnosis
│   ├── main_diagnose.py         # Entry point
│   ├── loader.py                # Data loading logic (Polars)
│   ├── analyzer.py              # Statistical analysis core
│   ├── visualizer.py            # Chart generation
│   └── report_generator.py      # Summary report builder
└── data\
    └── data_diagnose\           # Output directory
        ├── raw_analysis\
        ├── domain_analysis\
        ├── feature_analysis\
        └── comparison_report\
```

### 3.2. Core Analysis Modules

#### A. Data Loader (`loader.py`)
- **Technology**: Polars for high-performance I/O.
- **Function**: Scan target directories, filter files based on user criteria (Level 1 only for Raw), and lazy-load datasets for memory efficiency.

#### B. Statistical Analyzer (`analyzer.py`)
- **Metrics**:
    - **Basic**: Row count, Column count, Memory usage.
    - **Completeness**: Null count/percentage, Zero count/percentage, Infinite count.
    - **Distribution**: Mean, Std, Min, Max.
    - **Quantiles**: 1%, 5%, 25%, 50%, 75%, 95%, 99% (crucial for detecting clipping).
    - **Data Integrity**: Unique value counts (for categorical/ID columns like `ts_code`, `trade_date`).
- **Logic**:
    - Use Polars expressions for parallel computation.
    - Handle `NaN` vs `Null` explicitly.

#### C. Preprocessing Verification (Deep Dive)
- **Target**: Compare `Raw` vs `Domain` vs `Feature`.
- **Hypothesis**: The user suspects `utils_clean.py` and `build_domain_*.py` are over-clipping or filling zeros aggressively.
- **Check**:
    - Identify columns that exist in both Raw and Domain.
    - Calculate the "clipping ratio" (percentage of values at exactly Min/Max bounds).
    - Check for "Zero Inflation" (significant increase in zeros from Raw to Feature).

#### D. Visualization (`visualizer.py`)
- **Library**: `matplotlib` (with Chinese font support `SimHei` or similar) or `plotly` (interactive).
- **Charts**:
    - **Histograms**: Distribution of key numerical features.
    - **Box Plots**: Outlier visualization.
    - **Missing Matrix**: Heatmap of missing values.
    - **Comparison Plots**: Overlay Raw vs Processed distributions.

### 3.3. Implementation Steps

1.  **Environment Setup**:
    - Verify Conda environment and required packages (`polars`, `pyarrow`, `matplotlib`, `seaborn`, `openpyxl`).
    - Create necessary directories.

2.  **Code Implementation**:
    - **Step 1: Loader & Basic Stats**: Implement `loader.py` and `analyzer.py` to compute the metrics defined above.
    - **Step 2: Preprocessing Critique**: specific checks for `utils_clean.py` logic (e.g., `winsorize_series`, `clip_outliers`).
    - **Step 3: Visualization**: Implement `visualizer.py` to generate Chinese-labeled charts.
    - **Step 4: Reporting**: Aggregate findings into a Markdown or HTML summary.

3.  **Execution & Refinement**:
    - Run the diagnosis on the specified folders.
    - Analyze the output.
    - If significant data loss is found, propose specific modifications to `utils_clean.py` (e.g., relaxing clip bounds, using dynamic thresholds).

## 4. Specific Analysis of Existing Preprocessing Logic
Based on the provided code snippets:
- **`utils_clean.py`**:
    - `safe_div`: Uses `fill_value=np.nan` (default) or `0.0` (in usage). Risk: Silent zero-filling.
    - `clip_outliers`: Default `0.01` to `0.99`. This is standard but might be too aggressive for fat-tailed financial data (e.g., returns, volume spikes).
    - `winsorize_series`: Hard clipping at quantiles.
- **`build_domain_B_moneyflow.py`**:
    - `fill_missing_grouped`: Uses `ffill`. Risk: Propagating stale data.
    - `clip(-1.0, 1.0)`: Hard bounds for ratios. Risk: Valid extreme events (e.g., massive inflows) are capped, losing signal.
    - `fillna(0)`: Applied to imbalances. Risk: Treating missing data as "neutral" might be bias-inducing.

## 5. Deliverables
1.  **Python Scripts**: Modular, documented, high-performance.
2.  **Diagnostic Report**: Located in `data/data_diagnose`, containing:
    - `summary_statistics.csv`: All metrics for all files.
    - `distribution_plots/`: PNG/HTML files.
    - `data_quality_report.md`: Narrative summary of findings.
3.  **Recommendations**: Suggested changes to `src_data_domain_feature` to preserve information.

## 6. Execution Command
```powershell
D:/Total_Tools/miniforge3/Scripts/activate
conda activate universal
python d:\Trading\data_ever_26_3_14\src_data-diagnose\main_diagnose.py
```
