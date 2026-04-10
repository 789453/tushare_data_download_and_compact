import polars as pl
import os
import re

def check_columns():
    print("Starting comprehensive column check...")
    
    # 1. Load Real Data Schema
    data_dir = r"d:\Trading\data_ever_26_3_14\data\Raw_data"
    fina_path = os.path.join(data_dir, "fina_indicator.parquet")
    daily_path = os.path.join(data_dir, "daily_basic.parquet")
    
    try:
        fina_cols = set(pl.scan_parquet(fina_path).collect_schema().names())
        daily_cols = set(pl.scan_parquet(daily_path).collect_schema().names())
        print(f"Loaded {len(fina_cols)} financial columns and {len(daily_cols)} daily columns.")
    except Exception as e:
        print(f"Error loading data schema: {e}")
        return

    # 2. Extract Columns Used in Code
    code_files = [
        r"d:\Trading\data_ever_26_3_14\src_fundmental_factors\factor_library_quarter_polars.py",
        r"d:\Trading\data_ever_26_3_14\src_fundmental_factors\factor_library_daily_polars.py"
    ]
    
    used_cols = set()
    col_pattern = re.compile(r"pl\.col\(['\"](\w+)['\"]\)")
    
    # Also manual lists in get_fina_cols_polars
    # We will just parse the file content roughly
    
    for file_path in code_files:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # Find all pl.col('xxx')
            matches = col_pattern.findall(content)
            used_cols.update(matches)
            
            # Find list definitions like pos_cols = [...]
            # This is harder to regex perfectly, but we can look for quoted strings inside lists
            # Simplification: assume any quoted string that looks like a variable name might be a column
            # But that's too broad.
            
            # Let's focus on what failed: 'ebit_ps', 'profit_to_gr', etc.
            
    # Manually added columns from previous context that we know are being used
    # From factor_library_quarter_polars.py
    quarter_cols = [
        'roe', 'roe_dt', 'q_roe', 'q_dt_roe', 'roa', 'npta', 'roic',
        'grossprofit_margin', 'netprofit_margin', 'profit_to_gr',
        'ocfps', 'cfps', 'q_ocf_to_sales', 'ocf_yoy', 'cfps_yoy',
        'ocf_to_debt', 'ocf_to_shortdebt', 'tr_yoy', 'or_yoy',
        'netprofit_yoy', 'dt_netprofit_yoy', 'q_sales_yoy', 'q_op_qoq',
        'roe_yoy', 'bps_yoy', 'assets_turn', 'ar_turn', 'turn_days',
        'debt_to_assets', 'current_ratio', 'quick_ratio', 'cash_ratio',
        'ebitda', 'debt_to_eqt', 'tangibleasset_to_debt',
        'invest_capital', 'profit_to_op', 'ebit_ps', 'profit_to_op'
    ]
    
    # From daily
    daily_used = [
        'pe_ttm', 'pb', 'ps_ttm', 'dv_ttm', 'turnover_rate_f', 'volume_ratio', 'circ_mv', 'free_share', 'float_share'
    ]
    
    all_needed = set(quarter_cols + daily_used)
    
    # 3. Check against available
    available = fina_cols.union(daily_cols)
    
    missing = [c for c in all_needed if c not in available]
    
    print("\n" + "="*30)
    print("MISSING COLUMNS REPORT")
    print("="*30)
    if missing:
        for m in missing:
            print(f"[MISSING] {m}")
            # Suggest alternatives
            # Fuzzy match?
            candidates = [c for c in available if m in c or c in m] # simple substring
            if candidates:
                print(f"    Did you mean: {candidates}")
            else:
                # Try finding similar names
                import difflib
                matches = difflib.get_close_matches(m, available, n=3, cutoff=0.6)
                if matches:
                    print(f"    Possible alternatives: {matches}")
    else:
        print("All columns found!")
        
    print("\n" + "="*30)
    print("Verification Complete")
    print("="*30)

if __name__ == "__main__":
    check_columns()
