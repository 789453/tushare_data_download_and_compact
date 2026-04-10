import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np

def setup_plotting_style():
    """Setup matplotlib style for Chinese support."""
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'SimSun', 'Arial']
    plt.rcParams['axes.unicode_minus'] = False
    sns.set_style("whitegrid")

def plot_factor_performance(results, factor_name, ret_col='ret_1'):
    """
    Plot factor performance summary.
    """
    setup_plotting_style()
    
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle(f'Factor Performance: {factor_name}', fontsize=16)
    
    # 1. IC Series
    ic_series = results[f'{ret_col}_ic_series']
    rank_ic_series = results[f'{ret_col}_rank_ic_series']
    
    ax1 = axes[0, 0]
    #ic_series.plot(ax=ax1, alpha=0.5, label='IC')
    rank_ic_series.plot(ax=ax1, alpha=0.5, label='RankIC', color='blue')
    rank_ic_series.rolling(window=20).mean().plot(ax=ax1, label='RankIC MA20', color='orange')
    ax1.set_title(f'Rank IC Series ({ret_col})')
    ax1.legend()
    ax1.axhline(0, color='gray', linestyle='--')
    
    # 2. Cumulative IC
    ax2 = axes[0, 1]
    rank_ic_cumsum = rank_ic_series.cumsum()
    rank_ic_cumsum.plot(ax=ax2, color='green')
    ax2.set_title(f'Cumulative Rank IC ({ret_col})')
    
    # 3. Group Cumulative Returns
    ax3 = axes[1, 0]
    group_ret = results[f'{ret_col}_group_ret']
    
    # Calculate cumulative return
    # Fill nan with 0 for plotting
    cum_group_ret = (1 + group_ret.fillna(0)).cumprod() - 1
    
    cum_group_ret.plot(ax=ax3)
    ax3.set_title(f'Group Cumulative Returns ({ret_col})')
    ax3.legend(title='Group')
    
    # 4. Long-Short Cumulative Return
    ax4 = axes[1, 1]
    if 'long_short' in group_ret.columns:
        cum_ls = (1 + group_ret['long_short'].fillna(0)).cumprod() - 1
        cum_ls.plot(ax=ax4, color='red')
        ax4.set_title(f'Long-Short Cumulative Return ({ret_col})')
    else:
        ax4.text(0.5, 0.5, 'No Long-Short Data', ha='center', va='center')
    
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    return fig
