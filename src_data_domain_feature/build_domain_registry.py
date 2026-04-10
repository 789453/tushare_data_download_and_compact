from typing import List, Dict, Any
from config import DOMAIN_DATA_DIR
import pandas as pd

DOMAIN_FIELDS: List[Dict[str, Any]] = [
    # Domain A
    {"field_name": "ret_cc_1d", "domain": "A", "desc": "Daily return", "processing": "Winsorized (1%-99%)"},
    {"field_name": "gap_open", "domain": "A", "desc": "Overnight gap", "processing": "Winsorized (1%-99%)"},
    {"field_name": "intraday_range", "domain": "A", "desc": "Intraday range", "processing": "Winsorized (1%-99%)"},
    {"field_name": "volume_ratio_ln", "domain": "A", "desc": "Log volume ratio", "processing": "Log1p transformed"},
    {"field_name": "upper_shadow_ratio", "domain": "A", "desc": "Upper shadow", "processing": "None"},
    {"field_name": "lower_shadow_ratio", "domain": "A", "desc": "Lower shadow", "processing": "None"},
    
    # Domain B
    {"field_name": "net_mf_to_amount", "domain": "B", "desc": "Net moneyflow ratio", "processing": "Winsorized (1%-99%), Missing filled with 0"},
    {"field_name": "imb_sm_amt", "domain": "B", "desc": "Small order imbalance", "processing": "Missing filled with 0"},
    {"field_name": "imb_md_amt", "domain": "B", "desc": "Medium order imbalance", "processing": "Missing filled with 0"},
    {"field_name": "imb_lg_amt", "domain": "B", "desc": "Large order imbalance", "processing": "Missing filled with 0"},
    {"field_name": "imb_elg_amt", "domain": "B", "desc": "Extra large order imbalance", "processing": "Missing filled with 0"},
    {"field_name": "flow_divergence", "domain": "B", "desc": "Flow divergence", "processing": "Missing filled with 0"},
    
    # Domain C
    {"field_name": "price_pos_hist", "domain": "C", "desc": "Price position history", "processing": "Clipped [0, 1]"},
    {"field_name": "winner_rate_pct", "domain": "C", "desc": "Winner rate", "processing": "Clipped [0, 1]"},
    {"field_name": "chip_width_95_5", "domain": "C", "desc": "Chip width 90%", "processing": "Winsorized (1%-99%)"},
    {"field_name": "overhang_95", "domain": "C", "desc": "Overhang pressure", "processing": "Winsorized (1%-99%)"},
    
    # Domain E
    {"field_name": "intraday_trend_eff", "domain": "E", "desc": "Trend efficiency", "processing": "Clipped [-20, 20]"},
    {"field_name": "high_low_time_skew", "domain": "E", "desc": "High/Low time skew", "processing": "None"},
]

def build_domain_registry():
    print("Building Domain Registry...")
    df = pd.DataFrame(DOMAIN_FIELDS)
    
    output_path = DOMAIN_DATA_DIR / "domain_registry.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    df.to_csv(output_path, index=False)
    print(f"Domain Registry saved to {output_path}")

if __name__ == "__main__":
    build_domain_registry()
