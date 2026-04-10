import polars as pl

def get_fina_cols_polars() -> list:
    """Returns the comprehensive list of available columns from fina_indicator."""
    return [
        # 1. 盈利能力与质量 (Earnings Quality)
        'roe', 'roe_dt', 'q_roe', 'q_dt_roe',
        'roa', 'npta', 'roic',
        'grossprofit_margin', 'netprofit_margin',
        'profit_to_gr', 
        
        # 2. 现金流 (Cash Flow)
        'ocfps', 'cfps', 'q_ocf_to_sales', 'ocf_yoy', 'cfps_yoy',
        'ocf_to_debt', 'ocf_to_shortdebt',
        
        # 3. 成长与改善 (Growth & Improvement)
        'tr_yoy', 'or_yoy', 'netprofit_yoy', 'dt_netprofit_yoy', 
        'q_sales_yoy', 'q_op_qoq', 'roe_yoy', 'bps_yoy',
        
        # 4. 营运效率 (Efficiency)
        'assets_turn', 'ar_turn', 'turn_days',
        
        # 5. 杠杆与安全 (Leverage & Safety)
        'debt_to_assets', 'current_ratio', 'quick_ratio', 'cash_ratio',
        'ebitda', 'debt_to_eqt', 'tangibleasset_to_debt',
        
        # 6. 资本结构 (Capital Structure)
        'invest_capital', 'profit_to_op', 'interestdebt', 'ebit_ps',
        
        # 7. 研发 (R&D)
    ]

def add_quarterly_factors(lf: pl.LazyFrame) -> pl.LazyFrame:
    """
    Calculate quarterly fundamental factors (Lazy execution).
    """
    print("Calculating full set of quarterly factors...")
    
    # Calculate derived columns first
    lf = lf.with_columns([
        (pl.col('ebitda') / pl.col('interestdebt')).fill_nan(0).fill_null(0).alias('ebitda_to_debt')
    ])
    
    # 1. Base factors to rank (Higher is better)
    pos_cols = [
        'roe_dt', 'q_dt_roe', 'roic', 'netprofit_margin', 
        'q_ocf_to_sales', 'ocfps', 'dt_netprofit_yoy', 'q_op_qoq', 'roe_yoy',
        'assets_turn', 'ar_turn', 'current_ratio', 'ocf_to_debt',
        'ebit_ps', 'profit_to_op', 'ebitda_to_debt'
    ]
    
    # 2. Base factors to rank (Lower is better)
    neg_cols = [
        'debt_to_assets', 'turn_days', 'debt_to_eqt'
    ]
    
    rank_exprs = []
    
    # Apply industry rank per day and l2_name
    for col in pos_cols:
        expr = pl.col(col).rank("ordinal").over(['date', 'l2_name']) / pl.col(col).count().over(['date', 'l2_name'])
        rank_exprs.append(expr.alias(f'{col}_ind_rank'))
        
    for col in neg_cols:
        expr = (-pl.col(col)).rank("ordinal").over(['date', 'l2_name']) / pl.col(col).count().over(['date', 'l2_name'])
        rank_exprs.append(expr.alias(f'{col}_ind_rank'))
        
    # Extra: Growth consistency
    # (q_sales_yoy rank + dt_netprofit_yoy rank) / 2
    
    lf = lf.with_columns(rank_exprs)
    
    # Add growth consistency
    lf = lf.with_columns([
        ((pl.col('tr_yoy').rank("ordinal").over(['date', 'l2_name']) / pl.col('tr_yoy').count().over(['date', 'l2_name'])).fill_null(0) +
         (pl.col('dt_netprofit_yoy').rank("ordinal").over(['date', 'l2_name']) / pl.col('dt_netprofit_yoy').count().over(['date', 'l2_name'])).fill_null(0)
        ) / 2.0
    ]).with_columns([
        pl.col('tr_yoy').alias('growth_consistency_ind_rank') # Temporary alias to reuse logic if needed
    ])
    
    return lf

def add_composite_factors(lf: pl.LazyFrame) -> pl.LazyFrame:
    """
    Add composite factors using linear combinations of ranks.
    """
    # Requires ranks to be calculated first.
    
    # Ensure z20 ranks are present for anti-crowding
    lf = lf.with_columns([
        (pl.col('turn_f_z20').rank("ordinal").over(['date', 'l2_name']) / pl.col('turn_f_z20').count().over(['date', 'l2_name'])).alias('turn_f_z20_ind_rank'),
        (pl.col('vol_ratio_z20').rank("ordinal").over(['date', 'l2_name']) / pl.col('vol_ratio_z20').count().over(['date', 'l2_name'])).alias('vol_ratio_z20_ind_rank')
    ])
    
    # Composite Factors (Updated with available columns)
    composites = [
        # 1. Value-Quality: ep, bp, roe_dt, q_ocf_to_sales (replacing ocf_to_or)
        (
            0.35 * pl.col('ep_ttm_rank_ind_l2').fill_null(0) +
            0.25 * pl.col('bp_rank_ind_l2').fill_null(0) +
            0.20 * pl.col('roe_dt_ind_rank').fill_null(0) +
            0.20 * pl.col('q_ocf_to_sales_ind_rank').fill_null(0)
        ).alias('comp_value_quality'),
        
        # 2. Margin-Improvement
        (
            0.25 * pl.col('profit_to_gr').rank("ordinal").over(['date', 'l2_name']) / pl.col('profit_to_gr').count().over(['date', 'l2_name']).fill_null(0) +
            0.25 * pl.col('q_ocf_to_sales_ind_rank').fill_null(0) +
            0.25 * pl.col('q_op_qoq_ind_rank').fill_null(0) +
            0.25 * pl.col('dt_netprofit_yoy_ind_rank').fill_null(0)
        ).alias('comp_margin_improvement'),
        
        # 3. Anti-Crowded Value
        (
            0.40 * pl.col('bp_rank_ind_l2').fill_null(0) +
            0.30 * pl.col('div_ttm_rank_ind_l1').fill_null(0) -
            0.15 * pl.col('turn_f_z20_ind_rank').fill_null(0) -
            0.15 * pl.col('vol_ratio_z20_ind_rank').fill_null(0)
        ).alias('comp_anti_crowded_val'),
        
        # 4. Efficiency-Growth
        (
            0.30 * pl.col('assets_turn_ind_rank').fill_null(0) +
            0.20 * pl.col('ar_turn_ind_rank').fill_null(0) +
            0.20 * pl.col('turn_days_ind_rank').fill_null(0) + # Substitute inv_turn with turn_days (inverted rank)
            0.30 * pl.col('dt_netprofit_yoy_ind_rank').fill_null(0) # or tr_yoy rank
        ).alias('comp_efficiency_growth'),
        
        # 5. Quality-Safety
        (
            0.25 * pl.col('current_ratio_ind_rank').fill_null(0) +
            0.25 * pl.col('ocf_to_debt_ind_rank').fill_null(0) +
            0.25 * pl.col('ebitda_to_debt_ind_rank').fill_null(0) + # Restored ebitda_to_debt
            0.25 * pl.col('debt_to_assets_ind_rank').fill_null(0)
        ).alias('comp_quality_safety')
    ]
    
    lf = lf.with_columns(composites)
    return lf
