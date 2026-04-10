<br />

这四个域的字段结构如下。

## A 域：日频量价域

字段包括：

- `ret_cc_1d`
- `ret_oc_1d`
- `gap_open`
- `intraday_range`
- `upper_shadow_ratio`
- `lower_shadow_ratio`
- `turnover_free`
- `volume_ratio_ln`

这是最适合直接替代原来 Qlib `OPEN/CLOSE/HIGH/LOW/VOLUME/VWAP` 的一组原子型价量特征。\
但这里有一个必须前置处理的工程事实：\
`ret_cc_1d`、`gap_open`、`intraday_range` 的上界非常异常，比如 `ret_cc_1d` 的最大值达到 **2004.0**，`gap_open` 最大值也达到 **2004.0**，`intraday_range` 最大值达到 **662.999...**。这显然不是正常股票日收益或日振幅，而是由极端错误值、复牌异动、除权口径问题、前值异常或接口占位导致的。

这意味着：\
**A 域不能直接原样喂给 AlphaPROBE**。\
正确做法不是改算子，而是在数据加载器里增加域前的极值过滤与无效样本剔除。

## B 域：小中大单 + 资金流域

字段包括：

- `imb_sm_amt`
- `imb_md_amt`
- `imb_lg_amt`
- `imb_elg_amt`
- `net_mf_to_amount`
- `large_buy_share`
- `large_sell_share`
- `flow_divergence`

这个域整体质量比我预期更好。绝大多数变量分布区间合理，尤其四个 imbalance 都落在 `[-1,1]`，买卖盘占比变量落在 `[0,1]`，说明你的规范化设计是成功的。\
唯一需要注意的是：

- `net_mf_to_amount` 范围在 `[-1.147, 2.551]`，虽然不算离谱，但上尾略重；
- 全域缺失率约 **3.64%**，这不算高，但已经足够影响表达式训练路径。

所以 B 域的核心不是重构字段，而是建立**统一的缺失处理和样本对齐策略**。

## C 域：筹码分布域

字段包括：

- `close_vs_cost50`
- `close_vs_weight_avg`
- `chip_width_95_5`
- `chip_width_85_15`
- `overhang_95`
- `support_5`
- `winner_rate_pct`
- `price_pos_hist`

这个域从经济含义上很强，但统计上最危险。\
你这组字段里有几个明显的重尾或异常上界：

- `close_vs_cost50` 最低到 **-11.48**
- `chip_width_95_5` 最高到 **34.24**
- `overhang_95` 最高到 **33.83**
- `price_pos_hist` 最高到 **288.80**

其中 `price_pos_hist` 作为“价格在历史区间中的位置”，理论上应该接近 `[0,1]` 左右，出现 288 基本不可能是正常值。\
这说明 C 域必须在装入训练器前执行：

- 区间合理性校验
- 分位截断
- 必要的 NaN 化

否则 AlphaPROBE 会非常容易围绕这些极值构造出伪高分表达式。

## E 域：日级 intraday summary 域

字段包括：

- `hour1_ret`
- `lasthour_ret`
- `midday_reversal`
- `intraday_trend_eff`
- `hourly_volatility`
- `volume_concentration_pm`
- `vwap_close_bias_1h`
- `high_low_time_skew`

这个域的问题最集中在 `intraday_trend_eff`。它的范围是：

- 最小值约 **-3,000,000**
- 最大值约 **15,000,000**

这显然不可能是一个可直接用于表达式搜索的正常特征。\
这说明你在计算 `intraday_trend_eff` 时，分母 `sum(|ret_h|)` 可能有过小值甚至接近零的情况，虽然你加了 epsilon，但对于分钟/小时级低波动股票仍会炸出极值。

因此 E 域进入 AlphaPROBE 前，必须做两件事：

1. 把 `intraday_trend_eff` 在数据层做 clip，例如限制到 `[-20, 20]` 或按分位截断；
2. 或者直接改成更稳健版本，例如\
   \[\
   \frac{close-open}{\max(\sum|ret\_h|,\tau)}\
   ]\
   但你说现在不想改字段构造，只想改项目接入，那就至少要在加载阶段裁剪。

##
