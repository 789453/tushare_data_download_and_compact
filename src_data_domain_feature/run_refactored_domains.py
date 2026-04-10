import logging
import time
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent))

from build_domain_A_price_volume import build_domain_A
from build_domain_B_moneyflow import build_domain_B
from build_domain_C_chip import build_domain_C
from build_domain_D_fundamental import build_domain_D
from build_domain_E_intraday_summary import build_domain_E

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    start_time = time.time()
    logger.info("Starting Refactored Domain Build...")
    
    try:
        logger.info("Building Domain A (Price & Volume)...")
        build_domain_A()
        
        logger.info("Building Domain B (Moneyflow)...")
        build_domain_B()
        
        logger.info("Building Domain C (Chip)...")
        build_domain_C()
        
        logger.info("Building Domain D (Fundamental)...")
        build_domain_D()
        
        logger.info("Building Domain E (Intraday)...")
        build_domain_E()
        
        elapsed = time.time() - start_time
        logger.info(f"Refactored domains built in {elapsed:.2f} seconds.")
        
    except Exception as e:
        logger.error(f"Build failed: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()
