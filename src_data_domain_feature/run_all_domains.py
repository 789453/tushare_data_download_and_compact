import logging
import time
from build_feature_registry import build_registry
from build_domain_registry import build_domain_registry
from build_domain_A_price_volume import build_domain_A
from build_domain_B_moneyflow import build_domain_B
from build_domain_C_chip import build_domain_C
from build_domain_D_fundamental import build_domain_D
from build_domain_E_intraday_summary import build_domain_E
from build_model_panel import build_model_panel

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    start_time = time.time()
    logger.info("Starting Full Domain & Feature Build Pipeline...")
    
    try:
        # 1. Registries
        logger.info("Step 1/8: Building Feature & Domain Registries")
        build_registry()
        build_domain_registry()
        
        # 2. Domain A
        logger.info("Step 2/8: Building Domain A (Price & Volume)")
        build_domain_A()
        
        # 3. Domain B
        logger.info("Step 3/8: Building Domain B (Moneyflow)")
        build_domain_B()
        
        # 4. Domain C
        logger.info("Step 4/8: Building Domain C (Chip/CYQ)")
        build_domain_C()
        
        # 5. Domain E (Intraday)
        logger.info("Step 5/8: Building Domain E (Intraday Summary)")
        build_domain_E()
        
        # 6. Domain D (Fundamental/Model)
        logger.info("Step 6/8: Building Domain D (Fundamental)")
        build_domain_D()
        
        # 7. Model Panel
        logger.info("Step 7/8: Building Model Panel")
        build_model_panel()
        
        elapsed = time.time() - start_time
        logger.info(f"All tasks completed successfully in {elapsed:.2f} seconds.")
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()
