
import polars as pl
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from pathlib import Path
import logging
from typing import Dict, Any, List, Optional
import sys

# Add current directory to path so we can import config
sys.path.append(str(Path(__file__).parent))
from diagnose_config import *

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configure Font
try:
    font_prop = fm.FontProperties(fname=FONT_PATH)
    plt.rcParams['font.family'] = font_prop.get_name()
    plt.rcParams['axes.unicode_minus'] = False # Fix minus sign display
except Exception as e:
    logger.warning(f"Could not load custom font from {FONT_PATH}. Using default. Error: {e}")
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial']
    plt.rcParams['axes.unicode_minus'] = False

class DataDiagnoser:
    def __init__(self, file_path: Path, output_subdir: str = "default"):
        self.file_path = Path(file_path)
        self.file_name = self.file_path.name
        self.output_subdir = output_subdir
        self.df: Optional[pl.DataFrame] = None
        self.stats: Dict[str, Any] = {}
        
        # Output directory for this specific file's analysis
        self.file_out_dir = IMG_DIR / output_subdir / self.file_path.stem
        self.file_out_dir.mkdir(parents=True, exist_ok=True)

    def load_data(self):
        """Load data using Polars."""
        try:
            logger.info(f"Loading {self.file_path}...")
            # Use scan_parquet for lazy loading if needed, but for stats we usually need to compute.
            # Reading into memory for speed on analysis if memory permits.
            # Given "polars(可以加pyarrow)", read_parquet is efficient.
            self.df = pl.read_parquet(self.file_path)
            logger.info(f"Loaded {self.file_name}: shape {self.df.shape}")
            return True
        except Exception as e:
            logger.error(f"Failed to load {self.file_path}: {e}")
            return False

    def calculate_basic_stats(self) -> Dict[str, Any]:
        """Calculate basic statistics for all columns."""
        if self.df is None:
            return {}
        
        n_rows, n_cols = self.df.shape
        self.stats['rows'] = n_rows
        self.stats['cols'] = n_cols
        self.stats['memory_usage_mb'] = self.df.estimated_size("mb")
        
        col_stats = []
        
        for col in self.df.columns:
            try:
                c = self.df[col]
                dtype = str(c.dtype)
                
                # Nulls
                null_count = c.null_count()
                null_pct = (null_count / n_rows) * 100 if n_rows > 0 else 0
                
                # Zeros (only for numeric)
                zero_count = 0
                zero_pct = 0
                if c.dtype in [pl.Int8, pl.Int16, pl.Int32, pl.Int64, 
                               pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64, 
                               pl.Float32, pl.Float64]:
                    zero_count = (c == 0).sum()
                    zero_pct = (zero_count / n_rows) * 100 if n_rows > 0 else 0
                
                stats_entry = {
                    'column': col,
                    'dtype': dtype,
                    'null_count': null_count,
                    'null_pct': round(null_pct, 4),
                    'zero_count': zero_count,
                    'zero_pct': round(zero_pct, 4)
                }
                
                # Numeric Stats
                if c.dtype in [pl.Float32, pl.Float64, pl.Int32, pl.Int64]:
                    # Filter out nulls for stats
                    c_valid = c.drop_nulls()
                    if len(c_valid) > 0:
                        stats_entry.update({
                            'min': float(c_valid.min()),
                            'max': float(c_valid.max()),
                            'mean': float(c_valid.mean()),
                            'std': float(c_valid.std()) if len(c_valid) > 1 else 0.0,
                            'q01': float(c_valid.quantile(0.01)),
                            'q05': float(c_valid.quantile(0.05)),
                            'q25': float(c_valid.quantile(0.25)),
                            'q50': float(c_valid.quantile(0.50)),
                            'q75': float(c_valid.quantile(0.75)),
                            'q95': float(c_valid.quantile(0.95)),
                            'q99': float(c_valid.quantile(0.99)),
                        })
                        
                        # Infinite check
                        if c.dtype in [pl.Float32, pl.Float64]:
                            inf_count = c.is_infinite().sum()
                            stats_entry['inf_count'] = inf_count
                    else:
                        stats_entry.update({'min': None, 'max': None, 'mean': None, 'std': None})
                
                col_stats.append(stats_entry)
            except Exception as e:
                logger.error(f"Error processing column {col} in {self.file_name}: {e}")
                col_stats.append({'column': col, 'error': str(e)})

        self.stats['columns'] = col_stats
        return self.stats

    def plot_distributions(self, columns: List[str] = None):
        """Plot histograms for numeric columns."""
        if self.df is None:
            return
        
        # If no columns specified, plot all numeric
        if columns is None:
            columns = [c for c in self.df.columns if self.df[c].dtype in [pl.Float32, pl.Float64, pl.Int32, pl.Int64]]
            # Limit to top 20 to avoid overwhelming
            columns = columns[:20] 

        for col in columns:
            try:
                data = self.df[col].drop_nulls().to_numpy()
                if len(data) == 0:
                    continue
                
                plt.figure(figsize=(10, 6))
                plt.hist(data, bins=50, alpha=0.7, color='skyblue', edgecolor='black')
                plt.title(f"{col} 分布图 (File: {self.file_name})", fontproperties=font_prop)
                plt.xlabel("Value", fontproperties=font_prop)
                plt.ylabel("Frequency", fontproperties=font_prop)
                plt.grid(True, alpha=0.3)
                
                # Save
                safe_col_name = col.replace("/", "_").replace("\\", "_")
                out_path = self.file_out_dir / f"dist_{safe_col_name}.png"
                plt.savefig(out_path)
                plt.close()
            except Exception as e:
                logger.error(f"Failed to plot {col}: {e}")

    def generate_report(self) -> str:
        """Generate a markdown report for this file."""
        if not self.stats:
            return "No stats available."
            
        lines = [f"# Data Diagnosis Report: {self.file_name}", ""]
        lines.append(f"**Rows**: {self.stats.get('rows', 0)}")
        lines.append(f"**Cols**: {self.stats.get('cols', 0)}")
        lines.append(f"**Memory**: {self.stats.get('memory_usage_mb', 0):.2f} MB")
        lines.append("")
        lines.append("## Column Statistics")
        lines.append("| Column | Type | Null% | Zero% | Min | Mean | Max | Q01 | Q99 |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        
        for c in self.stats.get('columns', []):
            if 'error' in c:
                continue
            
            # Format numbers
            def fmt(v):
                return f"{v:.4f}" if isinstance(v, (float, int)) and not isinstance(v, bool) else str(v)
            
            row = [
                c['column'],
                c['dtype'],
                f"{c['null_pct']:.2f}%",
                f"{c['zero_pct']:.2f}%",
                fmt(c.get('min', '-')),
                fmt(c.get('mean', '-')),
                fmt(c.get('max', '-')),
                fmt(c.get('q01', '-')),
                fmt(c.get('q99', '-'))
            ]
            lines.append("| " + " | ".join(row) + " |")
            
        return "\n".join(lines)

def run_diagnose_for_file(file_path: Path, output_subdir: str) -> dict:
    diagnoser = DataDiagnoser(file_path, output_subdir)
    if diagnoser.load_data():
        diagnoser.calculate_basic_stats()
        diagnoser.plot_distributions()
        
        report = diagnoser.generate_report()
        report_path = diagnoser.file_out_dir / "report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
            
        return diagnoser.stats
    return {}

if __name__ == "__main__":
    # Test run
    pass
