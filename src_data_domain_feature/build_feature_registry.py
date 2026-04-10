import pandas as pd
from registry import FEATURES
from config import FEATURE_REGISTRY_PATH

def build_registry():
    print("Building Feature Registry...")
    df = pd.DataFrame(FEATURES)
    
    # Ensure directory exists
    FEATURE_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    df.to_csv(FEATURE_REGISTRY_PATH, index=False)
    print(f"Feature Registry saved to {FEATURE_REGISTRY_PATH}")

if __name__ == "__main__":
    build_registry()
