from transforms import ind_rank

def compose_factors(df):
    """
    Calculate composite factors using linear combinations of industry ranks.
    """
    print("Composing factors...")
    
    # Pre-rank needed columns if not already ranked
    if 'turn_f_z20_ind_rank' not in df.columns:
        df['turn_f_z20_ind_rank'] = ind_rank(df, 'turn_f_z20', ind_col='l2_name', min_n=5)
    if 'vol_ratio_z20_ind_rank' not in df.columns:
        df['vol_ratio_z20_ind_rank'] = ind_rank(df, 'vol_ratio_z20', ind_col='l2_name', min_n=5)
        
    # 1. Value-Quality
    df['comp_value_quality'] = (
        0.35 * df.get('ep_ttm_rank_ind_l2', 0) +
        0.25 * df.get('bp_rank_ind_l2', 0) +
        0.20 * df.get('roe_dt_ind_rank', 0) +
        0.20 * df.get('ocf_to_or_ind_rank', 0)
    )
    
    # 2. Margin-Improvement
    df['comp_margin_improvement'] = (
        0.25 * df.get('q_profit_to_gr_ind_rank', 0) +
        0.25 * df.get('q_ocf_to_sales_ind_rank', 0) +
        0.25 * df.get('q_op_qoq_ind_rank', 0) +
        0.25 * df.get('dt_netprofit_yoy_ind_rank', 0)
    )
    
    # 3. Anti-Crowded Value
    df['comp_anti_crowded_val'] = (
        0.40 * df.get('bp_rank_ind_l2', 0) +
        0.30 * df.get('div_ttm_rank_ind_l1', 0) -
        0.15 * df.get('turn_f_z20_ind_rank', 0) -
        0.15 * df.get('vol_ratio_z20_ind_rank', 0)
    )
    
    # 4. Efficiency-Growth
    df['comp_efficiency_growth'] = (
        0.30 * df.get('assets_turn_ind_rank', 0) +
        0.20 * df.get('ar_turn_ind_rank', 0) +
        0.20 * df.get('inv_turn_ind_rank', 0) +
        0.30 * df.get('q_sales_yoy_ind_rank', 0)
    )
    
    # 5. Quality-Safety
    # Note: debt_to_assets_ind_rank was already ranked on negative values (so higher rank = lower debt)
    df['comp_quality_safety'] = (
        0.25 * df.get('current_ratio_ind_rank', 0) +
        0.25 * df.get('ocf_to_debt_ind_rank', 0) +
        0.25 * df.get('ebitda_to_debt_ind_rank', 0) +
        0.25 * df.get('debt_to_assets_ind_rank', 0) 
    )
    
    return df
