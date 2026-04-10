import pandas as pd
import logging
from pathlib import Path
from typing import List, Optional, Union

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_parquet(file_path: Union[str, Path], columns: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Load parquet file efficiently using pyarrow engine.
    """
    path = Path(file_path)
    if not path.exists():
        logger.error(f"File not found: {path}")
        raise FileNotFoundError(f"File not found: {path}")
    
    logger.info(f"Loading {path.name}...")
    try:
        df = pd.read_parquet(path, columns=columns, engine='pyarrow')
        logger.info(f"Loaded {path.name}: {df.shape}")
        return df
    except Exception as e:
        logger.error(f"Error loading {path}: {e}")
        raise

def save_parquet(df: pd.DataFrame, file_path: Union[str, Path]) -> None:
    """
    Save dataframe to parquet file using pyarrow engine.
    """
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Saving to {path.name}...")
    try:
        df.to_parquet(path, index=False, engine='pyarrow', compression='snappy')
        logger.info(f"Saved {path.name}: {df.shape}")
    except Exception as e:
        logger.error(f"Error saving to {path}: {e}")
        raise
