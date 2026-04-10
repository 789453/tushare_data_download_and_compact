
import os
import sys
from pathlib import Path
import polars as pl
import pandas as pd
import logging
from datetime import datetime

# Add current directory to path
sys.path.append(str(Path(__file__).parent))

from diagnose_config import *
from diagnose_core import DataDiagnoser

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def scan_files(directory: Path, pattern: str = "*.parquet", recursive: bool = False) -> list[Path]:
    """Scan for files matching pattern."""
    if not directory.exists():
        logger.warning(f"Directory not found: {directory}")
        return []
    
    if recursive:
        return list(directory.rglob(pattern))
    else:
        return list(directory.glob(pattern))

def aggregate_results(all_stats: list[dict], output_file: Path):
    """Aggregate individual file stats into a master CSV."""
    rows = []
    for file_stat in all_stats:
        file_name = file_stat.get('file_name', 'unknown')
        group = file_stat.get('group', 'unknown')
        rows_count = file_stat.get('rows', 0)
        
        for col_stat in file_stat.get('columns', []):
            row = {
                'group': group,
                'file_name': file_name,
                'total_rows': rows_count,
                'column': col_stat.get('column'),
                'dtype': col_stat.get('dtype'),
                'null_pct': col_stat.get('null_pct'),
                'zero_pct': col_stat.get('zero_pct'),
                'min': col_stat.get('min'),
                'mean': col_stat.get('mean'),
                'max': col_stat.get('max'),
                'q01': col_stat.get('q01'),
                'q99': col_stat.get('q99'),
                'std': col_stat.get('std')
            }
            rows.append(row)
            
    if rows:
        df = pd.DataFrame(rows)
        df.to_csv(output_file, index=False, encoding='utf-8-sig')
        logger.info(f"Aggregated stats saved to {output_file}")
    else:
        logger.warning("No stats to aggregate.")

def generate_master_report(all_stats: list[dict], output_file: Path):
    """Generate a high-level markdown report."""
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# Global Data Diagnosis Report\n\n")
        f.write(f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        # Summary by Group
        f.write("## Dataset Summary\n")
        groups = {}
        for s in all_stats:
            g = s.get('group', 'unknown')
            if g not in groups:
                groups[g] = {'files': 0, 'rows': 0, 'size_mb': 0}
            groups[g]['files'] += 1
            groups[g]['rows'] += s.get('rows', 0)
            groups[g]['size_mb'] += s.get('memory_usage_mb', 0)
            
        f.write("| Group | Files | Total Rows | Total Size (MB) |\n")
        f.write("|---|---|---|---|\n")
        for g, data in groups.items():
            f.write(f"| {g} | {data['files']} | {data['rows']} | {data['size_mb']:.2f} |\n")
        f.write("\n")
        
        # Warnings / Anomalies
        f.write("## Potential Issues\n")
        f.write("The following columns have > 50% Nulls or > 90% Zeros:\n\n")
        
        for s in all_stats:
            file_name = s.get('file_name')
            issues = []
            for c in s.get('columns', []):
                if c.get('null_pct', 0) > 50:
                    issues.append(f"{c['column']} (Null: {c['null_pct']}%)")
                if c.get('zero_pct', 0) > 90:
                    issues.append(f"{c['column']} (Zero: {c['zero_pct']}%)")
            
            if issues:
                f.write(f"### {file_name}\n")
                for i in issues:
                    f.write(f"- {i}\n")
                f.write("\n")

def main():
    logger.info("Starting Data Diagnosis...")
    
    # Define tasks
    # (Path, Recursive, GroupName)
    tasks = [
        (RAW_DATA_DIR, False, "Raw_Data"),          # Level 1 only
        (FEATURE_READY_DIR, False, "Feature_Ready"),
        (DOMAIN_DATA_DIR, False, "Domain_Data")
    ]
    
    all_stats = []
    
    for directory, recursive, group_name in tasks:
        logger.info(f"Scanning {group_name} in {directory}...")
        files = scan_files(directory, "*.parquet", recursive)
        logger.info(f"Found {len(files)} files.")
        
        for file_path in files:
            logger.info(f"Processing {file_path.name}...")
            
            diagnoser = DataDiagnoser(file_path, output_subdir=group_name)
            if diagnoser.load_data():
                diagnoser.calculate_basic_stats()
                diagnoser.plot_distributions()
                
                # Save individual report
                indiv_report = diagnoser.generate_report()
                report_path = diagnoser.file_out_dir / "report.md"
                with open(report_path, "w", encoding="utf-8") as f:
                    f.write(indiv_report)
                
                # Collect stats
                stats = diagnoser.stats
                stats['file_name'] = file_path.name
                stats['group'] = group_name
                all_stats.append(stats)
            
    # Aggregate
    agg_file = OUTPUT_DIR / "all_data_stats.csv"
    aggregate_results(all_stats, agg_file)
    
    # Master Report
    master_report = OUTPUT_DIR / "diagnosis_summary.md"
    generate_master_report(all_stats, master_report)
    
    logger.info("Diagnosis Complete.")

if __name__ == "__main__":
    main()
