# Refactoring Plan: Data Pipeline Engineering

This plan details the steps to address data loss, clipping, and zero-filling issues across the domain data pipeline, based on the diagnostic report and architectural guidelines.

## 1. Core Utilities Refactoring (`utils_clean.py`)
- [ ] **Implement `WinsorizeStrategy` Enum**: Define explicit strategies (`NONE`, `QUANTILE`, `SIGMA`, `MAD`).
- [ ] **Enhance `winsorize_series`**: Add `strategy` parameter. Deprecate implicit 1%/99% clipping.
- [ ] **Enhance `safe_div`**: Ensure default is `NaN` (not 0) unless explicitly requested.
- [ ] **Add `check_data_quality`**: Helper to flag zeros/missings before calculation.

## 2. Domain E: Intraday Summary (`build_domain_E_intraday_summary.py`)
- [ ] **Fix `hour1_ret` Logic**:
    - Validate `hour` extraction logic.
    - Explicitly filter for 09:30-10:30 window.
    - Ensure `open` is from the *first minute* and `close` is from the *last minute* of the first hour.
    - Handle missing data: If no trade in first hour, return `NaN`.
- [ ] **Fix `hourly_volatility`**:
    - Remove hard 1% winsorization.
    - Use 5-sigma or MAD if outlier protection is needed.

## 3. Domain B: Moneyflow (`build_domain_B_moneyflow.py`)
- [ ] **Fix Zero-Filling**:
    - Remove `fillna(0)` for imbalances (`imb_*`).
    - Return `NaN` when `buy + sell == 0`.
    - Create `_is_valid` flags for these fields.
- [ ] **Fix Hard Clipping**:
    - Remove `clip(-1, 1)` for `net_mf_to_amount` and `flow_divergence`.
    - Allow natural range for `large_buy_share`.

## 4. Domain C: Chip Distribution (`build_domain_C_chip.py`)
- [ ] **Fix Boundary Clipping**:
    - Remove `clip(-1, 1)` for `close_vs_cost50`.
    - Allow wider range for `chip_width` (e.g., 0 to 10 or dynamic).
- [ ] **Fix Denominator Logic**:
    - Handle `cost_50pct` near zero or missing.

## 5. Domain A: Price & Volume (`build_domain_A_price_volume.py`)
- [ ] **Fix Return Clipping**:
    - Remove 10% hard clip on `ret_cc_1d`.
    - Remove 0.5 clip on `ret_oc_1d`.
    - Use logic-based validation (e.g., check against price limits if available, or just rely on raw data).
- [ ] **Fix Shadow Ratios**:
    - Check if `range_hl` is zero.

## 6. Verification
- [ ] Re-run diagnosis script on `Feature_Ready` and `Domain` folders.
- [ ] Compare `all_data_stats.csv` before and after.
- [ ] Verify `hour1_ret` zero count significantly reduced.
- [ ] Verify extreme values in `ret_cc_1d` are restored.
