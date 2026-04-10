
import json
import re
import os
import ast

def load_json_keys(filepath):
    """Load the first item from json and return its keys."""
    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found.")
        return set()
    
    with open(filepath, 'r', encoding='utf-8') as f:
        # Read a chunk to avoid loading huge file if it is huge
        # But here it is likely a list of dicts.
        try:
            data = json.load(f)
            if isinstance(data, list) and len(data) > 0:
                return set(data[0].keys())
            elif isinstance(data, dict):
                return set(data.keys())
        except Exception as e:
            print(f"Error loading json: {e}")
            return set()
    return set()

def extract_list_from_code(filepath, list_name):
    """Extract a list definition from python code using AST."""
    with open(filepath, 'r', encoding='utf-8') as f:
        tree = ast.parse(f.read())
    
    found_items = set()
    
    for node in ast.walk(tree):
        # Check for direct list assignment: list_name = [...]
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == list_name:
                    if isinstance(node.value, ast.List):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant): # python 3.8+
                                found_items.add(elt.value)
                            elif isinstance(elt, ast.Str): # python < 3.8
                                found_items.add(elt.s)
    
    return found_items

def extract_return_list_from_func(filepath, func_name):
    """Extract the list returned by a specific function."""
    with open(filepath, 'r', encoding='utf-8') as f:
        tree = ast.parse(f.read())
        
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            for subnode in ast.walk(node):
                if isinstance(subnode, ast.Return):
                    if isinstance(subnode.value, ast.List):
                        items = set()
                        for elt in subnode.value.elts:
                            if isinstance(elt, ast.Constant):
                                items.add(elt.value)
                            elif isinstance(elt, ast.Str):
                                items.add(elt.s)
                        return items
    return set()

def extract_pl_col_usages(filepath):
    """Extract strings inside pl.col('...') using regex."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Match pl.col('name') or pl.col("name")
    matches = re.findall(r"pl\.col\(['\"]([^'\"]+)['\"]\)", content)
    return set(matches)

def main():
    base_dir = r"d:\Trading\data_ever_26_3_14"
    json_path = os.path.join(base_dir, r"data\Raw_data\fina_indicator.json")
    quarter_lib_path = os.path.join(base_dir, r"src_fundmental_factors\factor_library_quarter_polars.py")
    daily_lib_path = os.path.join(base_dir, r"src_fundmental_factors\factor_library_daily_polars.py")
    
    # 1. Get available fields
    available_fields = load_json_keys(json_path)
    print(f"Loaded {len(available_fields)} fields from fina_indicator.json")
    
    # 2. Check Quarter Library
    print(f"\nAnalyzing {quarter_lib_path}...")
    
    # 2a. Check get_fina_cols_polars return list
    declared_cols = extract_return_list_from_func(quarter_lib_path, "get_fina_cols_polars")
    missing_in_data = declared_cols - available_fields
    
    print("\n--- 1. Declared Columns NOT in Data (fina_indicator.json) ---")
    if missing_in_data:
        for col in sorted(missing_in_data):
            print(f"  [MISSING DATA] {col}")
    else:
        print("  None")

    # 2b. Check usage in pos_cols and neg_cols vs Declared
    pos_cols = extract_list_from_code(quarter_lib_path, "pos_cols")
    neg_cols = extract_list_from_code(quarter_lib_path, "neg_cols")
    
    all_ranking_cols = pos_cols.union(neg_cols)
    
    # These columns MUST be in declared_cols (if they are raw) or be created before usage.
    # We assume they are raw if they are in available_fields.
    
    print("\n--- 2. Ranking Columns NOT Declared in get_fina_cols_polars ---")
    print("(These will cause ColumnNotFoundError if they are raw data columns)")
    
    for col in sorted(all_ranking_cols):
        if col not in declared_cols:
            if col in available_fields:
                print(f"  [MISSING DECLARATION] {col} (Exists in data, but not selected in get_fina_cols_polars)")
            else:
                # It might be a calculated column (e.g. intermediate) or a typo
                print(f"  [UNKNOWN] {col} (Not in data, not declared. Typo or intermediate?)")

    # 2c. Check composite factors
    # We can extract pl.col usages inside add_composite_factors?
    # For now, let's focus on the ranking cols as that was the error source.


    # 3. Check Daily Library (just for completeness, though likely uses different source)
    print(f"\nAnalyzing {daily_lib_path}...")
    daily_used_cols = extract_pl_col_usages(daily_lib_path)
    # daily library mostly uses daily_basic.parquet, not fina_indicator.
    # But we can check if any look like fina columns that are missing.
    
    # Generate Report
    report_path = os.path.join(base_dir, r"data\Fundmental_data\field_check_report.md")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("# Field Check Report\n\n")
        f.write("## 1. Declared Columns NOT in Data (fina_indicator.json)\n")
        f.write("These columns are requested from `fina_indicator` but do not exist in the JSON.\n\n")
        if missing_in_data:
            for col in sorted(missing_in_data):
                f.write(f"- **{col}**\n")
        else:
            f.write("None.\n")
            
        f.write("\n## 2. Ranking Columns NOT Declared in get_fina_cols_polars\n")
        f.write("These columns are used in `pos_cols`/`neg_cols` but not selected from data. This causes errors.\n\n")
        
        found_issues = False
        for col in sorted(all_ranking_cols):
            if col not in declared_cols:
                found_issues = True
                if col in available_fields:
                    f.write(f"- **{col}**: Exists in data, but **MISSING** from `get_fina_cols_polars`.\n")
                else:
                    f.write(f"- **{col}**: **NOT** in data and **NOT** declared. (Calculated or Typo?)\n")
        
        if not found_issues:
            f.write("None.\n")

    # Dump all available fields for manual inspection
    with open(os.path.join(base_dir, r"data\Fundmental_data\available_fields.txt"), 'w') as f:
        for col in sorted(available_fields):
            f.write(f"{col}\n")
            
    print(f"\nReport generated at {report_path}")

if __name__ == "__main__":
    main()
