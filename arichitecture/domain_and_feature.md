下面这份文档，我按“ **可直接落地到你的工程目录** ”来写，不讲空泛原则，直接回答四件事：

1. 你这 5 份原始 parquet 应该怎样拆成 5 个域。
2. 每个域具体保留哪些 **衍生字段** ，每个域给出  **6–8 个核心字段** ，且这些字段都可以直接喂给 AlphaPROBE， **不再喂原始字段** 。
3. **D. 基本面 / 估值 / 财务域** 不进入 AlphaPROBE，但要单独做成可供模型层使用的标准域，我会结合 5 个接口文档里的字段含义具体展开。
4. 给出一份完整的  **Feature Registry 规范** 、目录结构、parquet 产物约定、以及 `src_data_domain_feature` 下代码文件应该怎么拆。

先把数据边界钉死。你现在手里的 5 个源文件对应 5 类数据接口：

* `daily`：A 股日线行情，字段是 `open/high/low/close/pre_close/change/pct_chg/vol/amount`，停牌期间 **不提供数据** ，这是交易可得性判断的重要前提。
* `daily_basic`：每日基本面/估值指标，字段包括 `turnover_rate/turnover_rate_f/volume_ratio/pe/pe_ttm/pb/ps/ps_ttm/dv_ratio/dv_ttm/total_share/float_share/free_share/total_mv/circ_mv`，属于 **日级更新的基本面与估值横截面** 。
* `moneyflow`：个股资金流向，覆盖 2010 年起，小中大特大单买卖量、买卖额、净流入量与净流入额。Tushare 明确给出了单笔成交额分层标准：小单 <5 万，中单 5–20 万，大单 20–100 万，特大单 ≥100 万。
* `cyq_perf`：每日筹码及胜率，覆盖 2018 年起，字段包括 `his_low/his_high/cost_5pct/cost_15pct/cost_50pct/cost_85pct/cost_95pct/weight_avg/winner_rate`。它描述的是 **历史价格区间、筹码成本分位、加权成本和获利盘比例** 。
* `stk_mins`：历史分钟行情，可取 `1min/5min/15min/30min/60min`，字段是 `trade_time/open/high/low/close/vol/amount`。你现在准备用 1h 级别做融合，我建议只把它压成 **日级 intraday summary 域** 。

你之前已经非常明确地提出了一个核心原则：**在因子挖掘阶段追求可解释、低维、互补；在模型阶段追求非线性与交互。** 我完全支持这个原则，而且它和你当前工程目标最匹配。你的搜索空间是超指数的，如果让 AlphaPROBE 直接面对“量价 + 订单流 + 筹码 + 估值 + 多频率 bar”的原始叶子集合，绝大多数训练预算都会消耗在冗余和低质量表达式上。把数据主动拆成域，再把每个域压成一小组“规范字段”，是最正确的做法。

---

# 一、总的工程结论：采用“Raw → Domain → Feature → Model”四层结构

我建议你把这次数据工程彻底定成下面四层，而不是只说“做几个 parquet”。

## 1. Raw 层

位置：`data/Raw_data/`

保存你已经下载好的 5 个 parquet，不覆盖、不二次加工：

* `daily.parquet`
* `daily_basic.parquet`
* `moneyflow.parquet`
* `cyq_perf.parquet`
* `stk_60_mins.parquet`

Raw 层的唯一目标是： **可追溯、可重建、可校验** 。后面任何域特征出现异常，都可以回到 Raw 对照。

## 2. Domain 层

位置：`data/Feature_data/domain/`

这一层是“按经济语义和频率拆开的中间域表”，每个表保留：

* 主键：`ts_code`, `trade_date`
* 域内需要的必要原始字段
* 不做过多模型化，只做清洗、对齐、最小限度的衍生

建议输出：

* `domain_price_volume_daily.parquet`
* `domain_moneyflow_daily.parquet`
* `domain_chip_daily.parquet`
* `domain_fundamental_daily.parquet`
* `domain_intraday_1h_summary.parquet`

## 3. Feature 层

位置：`data/Feature_data/factor_ready/`

这一层输出的是 **给因子挖掘用的规范字段表** 。
也就是：A、B、C、E 四个域分别输出一份， **只包含衍生字段，不再包含原始字段** 。

建议输出：

* `feature_A_price_volume.parquet`
* `feature_B_moneyflow.parquet`
* `feature_C_chip.parquet`
* `feature_E_intraday_summary.parquet`

## 4. Model 层

位置：`data/Model_data/`

这一层做横向 join，产出给 ridge / LightGBM / XGBoost / DL 使用的模型输入表。
D 域（基本面 / 估值 / 财务）主要在这里发挥作用。

建议输出：

* `model_domain_D_fundamental.parquet`
* `model_all_domains_daily.parquet`
* `model_train_panel.parquet`

---

# 二、统一数据主键与交易日历规则

这部分必须先定，否则你后面所有 parquet 都会不断返工。

## 主键

全部域统一使用：

* `ts_code`
* `trade_date`

其中分钟数据先从 `trade_time` 提取日级 `trade_date`，再聚合。

## 交易日期规则

以 `daily.parquet` 为主日历。原因很简单：
Tushare 的 `daily` 明确说明停牌期间不提供数据，所以只要 `daily` 上没有该股票该日记录，就不该把它视作正常交易样本。

这带来两个非常重要的工程约束：

1. 其他域与 `daily` 对齐时，必须以 `daily` 的 `(ts_code, trade_date)` 为主表。
2. 不允许从 `daily_basic`、`moneyflow`、`cyq_perf` 反向“补出”一个实际上在日线交易上不存在的样本。

这会让你的“停牌、退市、不可交易日”处理天然稳健很多。

---

# 三、五个域的设计方案

下面进入核心部分。我会分别给出：

* 域的定位
* 原始来源
* 是否进入 AlphaPROBE
* 6–8 个最终衍生字段
* 字段定义公式
* 为什么这样做

---

## A. 日频量价域

## 1）域定位

这是你的主基础域，负责提供最通用、最稳健、最适合表达式挖掘的日频价格—成交特征。

原始来源：

* `daily`: `open/high/low/close/pre_close/change/pct_chg/vol/amount`
* `daily_basic`: `turnover_rate/turnover_rate_f/volume_ratio` 可并入这个域，因为它们本质上是交易活跃度与量价配套指标。

## 2）是否进入 AlphaPROBE

**进入。**

## 3）不喂原始字段，最终保留的 8 个衍生字段

### A1. `ret_cc_1d`

定义：
[
ret_cc_1d = \frac{close}{pre_close} - 1
]

说明：最基本的日收益。虽然 `pct_chg` 已经存在，但统一由你自己计算更稳，避免接口字段口径差异。

### A2. `ret_oc_1d`

定义：
[
ret_oc_1d = \frac{close}{open} - 1
]

说明：日内方向，区分“高开低走”与“低开高走”。

### A3. `gap_open`

定义：
[
gap_open = \frac{open}{pre_close} - 1
]

说明：隔夜信息与开盘定价偏移。

### A4. `intraday_range`

定义：
[
intraday_range = \frac{high-low}{pre_close + \epsilon}
]

说明：真实振幅，比单独 high/low 更适合横截面比较。

### A5. `upper_shadow_ratio`

定义：
[
upper_shadow_ratio = \frac{high-\max(open, close)}{high-low+\epsilon}
]

说明：上影线强度，反映盘中抛压。

### A6. `lower_shadow_ratio`

定义：
[
lower_shadow_ratio = \frac{\min(open, close)-low}{high-low+\epsilon}
]

说明：下影线强度，反映盘中承接。

### A7. `turnover_free`

定义：
直接使用 `turnover_rate_f / 100`

说明：自由流通换手比总换手更有交易意义。`daily_basic` 明确给出了 `turnover_rate_f`。

### A8. `volume_ratio_ln`

定义：
[
volume_ratio_ln = \log(1 + volume_ratio)
]

说明：量比本身右偏严重，先做 log 更稳。`volume_ratio` 来自 `daily_basic`。

## 4）为什么这 8 个字段适合挖掘

这组字段的共同特点是：

* 全部无量纲；
* 都是单日可解释原子；
* 没有引入技术指标；
* 允许 AlphaPROBE 用你已有算子做时序组合，而不需要你新增语法。

也就是说，你把“原始日线 K 线”先压成了 **更适合表达式搜索的原子砖块** 。

---

## B. 小中大单 + 资金流域

## 1）域定位

这个域不是简单描述“成交大不大”，而是要描述：

* 主动买卖方向；
* 大小单之间的分歧；
* 净流入强度；
* 订单流相对流动性的偏离。

Tushare 的 `moneyflow` 给的是按主动买卖划分、按单笔成交额分层的统计。这个语义非常强，但绝对金额和绝对手数都不能直接喂给挖掘。

## 2）是否进入 AlphaPROBE

**进入。**

## 3）最终保留的 8 个衍生字段

### B1. `imb_sm_amt`

定义：
[
imb_sm_amt = \frac{buy_sm_amount - sell_sm_amount}{buy_sm_amount + sell_sm_amount + \epsilon}
]

### B2. `imb_md_amt`

定义同上，替换为 `md`.

### B3. `imb_lg_amt`

定义同上，替换为 `lg`.

### B4. `imb_elg_amt`

定义同上，替换为 `elg`.

说明：四个层级的主动买卖不平衡，是这个域最核心的原子。

### B5. `net_mf_to_amount`

定义：
[
net_mf_to_amount = \frac{net_mf_amount}{amount + \epsilon}
]

说明：净流入额占当日成交额的比例。这里的 `amount` 用日线成交额主表对齐。`moneyflow` 的 `net_mf_amount` 单位是万元，`daily` 的 `amount` 单位是千元，因此你实现时要先统一单位。两个接口文档单位并不一致，这一步必须显式写在代码里。

### B6. `large_buy_share`

定义：
[
large_buy_share = \frac{buy_lg_amount + buy_elg_amount}{buy_sm_amount + buy_md_amount + buy_lg_amount + buy_elg_amount + \epsilon}
]

说明：主动买盘中，大资金占比多少。

### B7. `large_sell_share`

定义同理，针对卖盘。

### B8. `flow_divergence`

定义：
[
flow_divergence = imb_elg_amt - imb_sm_amt
]

说明：特大单与小单之间的方向差。
如果特大单在买、小单在卖，这个值会很高，常常比单看 `net_mf` 更有信息。

## 4）为什么不保留原始手数和金额

因为原始金额首先编码的是市值、成交活跃度与股价水平，而不是资金方向。
你真正想让 AlphaPROBE 学的是“方向、分层、强弱、分歧”，而不是“这个股票今天本来就很大”。

---

## C. 筹码分布域

## 1）域定位

`cyq_perf` 不是普通价格数据，它是 **持仓成本分布与获利盘状态** 。从字段定义看，核心信息来自：

* 成本分位；
* 加权平均成本；
* 历史高低位；
* 胜率。

## 2）是否进入 AlphaPROBE

**进入。**

## 3）最终保留的 8 个衍生字段

### C1. `close_vs_cost50`

定义：
[
close_vs_cost50 = \frac{close - cost_{50pct}}{close + \epsilon}
]

说明：现价相对中位筹码成本的位置。

### C2. `close_vs_weight_avg`

定义：
[
close_vs_weight_avg = \frac{close - weight_avg}{close + \epsilon}
]

说明：现价相对平均持仓成本的位置。

### C3. `chip_width_95_5`

定义：
[
chip_width_{95_5} = \frac{cost_{95pct} - cost_{5pct}}{close + \epsilon}
]

说明：筹码分布宽度，越宽表示持仓成本分散、筹码不集中。

### C4. `chip_width_85_15`

定义：
[
chip_width_{85_15} = \frac{cost_{85pct} - cost_{15pct}}{close + \epsilon}
]

说明：更稳健的中部宽度。

### C5. `overhang_95`

定义：
[
overhang_{95} = \frac{cost_{95pct} - close}{close + \epsilon}
]

说明：上方高成本筹码压力。

### C6. `support_5`

定义：
[
support_{5} = \frac{close - cost_{5pct}}{close + \epsilon}
]

说明：下方低成本筹码垫。

### C7. `winner_rate_pct`

定义：
[
winner_rate_pct = winner_rate / 100
]

说明：直接把获利盘比例缩到 0–1 区间。

### C8. `price_pos_hist`

定义：
[
price_pos_hist = \frac{close - his_low}{his_high - his_low + \epsilon}
]

说明：现价在历史全区间中的相对位置。

## 4）为什么这组字段适合因子挖掘

因为它们全部把筹码原始价格量纲转成了 **相对位置、相对宽度、相对压力** 。
AlphaPROBE 最擅长在这种“语义清晰的原子特征”上做时序变换，而不是在 `cost_15pct`、`cost_95pct` 这样的原始价格量上盲目拼接。

---

## D. 基本面 / 估值 / 财务域

这一部分你特别要求“ **具体结合 5 个文档中的内容字段和含义** ”。我分两层讲：先讲 **为什么 D 域不进入 AlphaPROBE** ，再讲 **具体应该怎么构建** 。

## 1）为什么 D 域不进 AlphaPROBE

你的判断是对的：这类字段大多数不适合让表达式树去做很复杂的结构搜索。原因有三个：

### 第一，更新频率慢

`daily_basic` 虽然是日更，但它的很多字段经济含义仍然更接近“慢变量”：

* `pe/pe_ttm/pb/ps/ps_ttm`
* `dv_ratio/dv_ttm`
* `total_share/float_share/free_share`
* `total_mv/circ_mv`

这些变量与量价、订单流、筹码相比，短期形态变化没有那么丰富。

### 第二，横截面排序意义强于时序组合意义

这类字段更有价值的，不是深层表达式，而是：

* 行业内分位；
* 变化率；
* 与规模、流动性的关系；
* 滞后对齐后的截面状态。

### 第三，它们更适合模型层做非线性组合

比如：

* 低 PB 在高换手还是低换手环境下更有效；
* 高股息在熊市还是震荡市中更有效；
* 高估值但资金流入持续转强时是否形成成长风格切换。

这类问题更适合树模型与组合器处理。

## 2）D 域原始字段含义梳理

来自 `daily_basic` 的关键字段含义很明确：

* `turnover_rate`, `turnover_rate_f`：换手率
* `volume_ratio`：量比
* `pe`, `pe_ttm`：市盈率
* `pb`：市净率
* `ps`, `ps_ttm`：市销率
* `dv_ratio`, `dv_ttm`：股息率
* `total_share`, `float_share`, `free_share`：股本结构
* `total_mv`, `circ_mv`：总市值、流通市值

而你之前总表里也已经把这些字段作为“动态连续变量”纳入统一面板。

## 3）D 域的构建原则

### 原则一：D 域不喂原始估值量纲，喂“慢变量表达”

### 原则二：显式保留行业相对位置

### 原则三：对财务/估值字段采用“滞后 + 分位 + 变化率”

### 原则四：D 域只进模型，不进 AlphaPROBE

## 4）建议保留的 8 个 D 域字段

注意，这 8 个不是给 AlphaPROBE 的，是给 `data/Model_data/model_domain_D_fundamental.parquet` 的。

### D1. `pe_ttm_rank_ind`

定义：行业内 `pe_ttm` 截面分位

### D2. `pb_rank_ind`

定义：行业内 `pb` 截面分位

### D3. `ps_ttm_rank_ind`

定义：行业内 `ps_ttm` 截面分位

### D4. `dv_ttm_rank_mkt`

定义：全市场 `dv_ttm` 截面分位

### D5. `mv_rank_mkt`

定义：全市场 `total_mv` 截面分位

### D6. `free_float_ratio`

定义：
[
free_float_ratio = \frac{free_share}{total_share + \epsilon}
]

### D7. `circ_mv_to_total_mv`

定义：
[
circ_mv_to_total_mv = \frac{circ_mv}{total_mv + \epsilon}
]

### D8. `valuation_compress_score`

定义：
一个组合分数，例如
[
valuation_compress_score = -0.4\cdot pe_ttm_rank_ind -0.4\cdot pb_rank_ind -0.2\cdot ps_ttm_rank_ind
]

说明：不是给 AlphaPROBE，而是给模型一个低维价值风格代理。

## 5）为什么 D 域这样做最合理

因为你要的不是“让 AlphaPROBE 在估值字段里再造公式”，而是让模型层拥有一组：

* 稳定；
* 慢变；
* 行业可比；
* 低维；
* 可解释

的估值与基本面状态变量。

这和你之前的判断完全一致：**基本面更适合 lag、Δ、行业相对分位，再交给模型融合。**

---

## E. 日级 intraday summary 域

## 1）域定位

这个域是你 1h 级别分钟数据的 **日内摘要压缩层** 。
不是原始 bar，不是逐小时序列，而是“把日内微结构压成几个日级字段”。

分钟接口支持多频率，但你当前最合理的是先从 `60min` 压缩。

## 2）是否进入 AlphaPROBE

**进入。**

## 3）最终保留的 8 个衍生字段

假设你用 1h bars 聚合，每天大致有 4 个交易小时块。

### E1. `hour1_ret`

定义：
首小时收盘相对首小时开盘收益。

### E2. `lasthour_ret`

定义：
尾小时收盘相对尾小时开盘收益。

### E3. `midday_reversal`

定义：
[
midday_reversal = lasthour_ret - hour1_ret
]

说明：早盘强、尾盘弱还是反过来。

### E4. `intraday_trend_eff`

定义：
[
intraday_trend_eff = \frac{close_{day}-open_{day}}{\sum_{h}|ret_h| + \epsilon}
]

说明：日内价格路径效率，越接近 1 说明趋势性越强。

### E5. `hourly_volatility`

定义：
1h 收益序列标准差。

### E6. `volume_concentration_pm`

定义：
[
volume_concentration_pm = \frac{\text{下午成交量}}{\text{全天成交量}+\epsilon}
]

### E7. `vwap_close_bias_1h`

定义：
[
vwap_close_bias_{1h} = \frac{close_{day} - vwap_{1h,day}}{close_{day}+\epsilon}
]

### E8. `high_low_time_skew`

定义：
最高价出现时间索引减最低价出现时间索引，再做归一。

说明：帮助区分“先杀后拉”与“先冲后落”的日内路径。

## 4）为什么不直接把 1h 原始 bars 喂给挖掘框架

因为那样会把你的叶子集合与表达式复杂度直接炸开。
AlphaPROBE 当前你不准备改语法，这就更说明： **多频率信息要在数据端先压缩成日摘要** ，而不是把问题推给挖掘器。

---

# 四、Feature Registry 设计

你之前自己已经把最关键的一句话说出来了：**先把 Feature Registry 做出来，一次性工程，后面省无数时间。** 我完全认同。

下面给你一份最实用的注册表结构。

## 文件位置

`data/Feature_data/feature_registry.csv`

## 必备字段

* `feature_name`
* `domain`：A/B/C/D/E
* `source_table`
* `freq`
* `entity_key`
* `time_key`
* `source_columns`
* `formula_desc`
* `unit_type`
* `value_type`
* `allow_in_alphaprobe`
* `allow_in_model`
* `fill_policy`
* `clip_policy`
* `neutralize_policy`
* `start_date`
* `notes`

## 示例条目

| feature_name       | domain | source_columns               | formula_desc             | allow_in_alphaprobe | allow_in_model | fill_policy                | neutralize_policy |
| ------------------ | ------ | ---------------------------- | ------------------------ | ------------------: | -------------: | -------------------------- | ----------------- |
| ret_cc_1d          | A      | close, pre_close             | close/pre_close-1        |                   1 |              1 | none                       | none              |
| turnover_free      | A      | turnover_rate_f              | turnover_rate_f/100      |                   1 |              1 | none                       | optional_cs       |
| imb_lg_amt         | B      | buy_lg_amount,sell_lg_amount | imbalance large amount   |                   1 |              1 | zero_if_both_zero_else_nan | none              |
| net_mf_to_amount   | B      | net_mf_amount,amount         | net inflow over turnover |                   1 |              1 | nan_if_amount_zero         | optional_cs       |
| close_vs_cost50    | C      | close,cost_50pct             | close-cost50 over close  |                   1 |              1 | ffill_1d_if_single_gap     | none              |
| winner_rate_pct    | C      | winner_rate                  | winner_rate/100          |                   1 |              1 | clip_0_1                   | none              |
| pb_rank_ind        | D      | pb,industry                  | within-industry rank     |                   0 |              1 | industry_median            | industry_rank     |
| intraday_trend_eff | E      | 1h close/open                | daily trend efficiency   |                   1 |              1 | none                       | none              |

这里最关键的不是表面字段，而是这三个控制位：

* `allow_in_alphaprobe`
* `allow_in_model`
* `neutralize_policy`

它们决定了你的数据工程和挖掘工程能不能彻底解耦。

---

# 五、标准化、中性化、异常处理放在哪

你之前最纠结的点之一，就是 zscore 到底在哪一步做。我这里给最终落地规则。

## 对 Feature_data/factor_ready

**不要预先做行业中性化和全截面 zscore 后再保存。**

原因很简单：
A/B/C/E 域是给 AlphaPROBE 的“原子字段域”。如果你在数据端就把所有东西都中性化、zscore 化，很多时序关系和原始相对关系会被抹掉。

所以对 `Feature_data`：

* 做最小限度的量纲统一；
* 做异常值裁剪；
* 不做最终横截面标准化。

## 对 Model_data

D 域，以及最终多域模型输入表，可以输出两版：

* `*_raw.parquet`
* `*_csnorm.parquet`

其中 `csnorm` 版可做：

1. 截面 winsor
2. 截面 robust zscore
3. 可选行业中性残差

这与你之前的判断一致：**行业中性化更适合放在评估层与模型层，而不是语法层。**

## 异常处理建议

* 分位裁剪优先于机械 3 sigma
* 对价格类先做规则检查
* 对比例类裁剪到合理区间
* `up_limit/down_limit` 如出现占位异常值，先设 NaN 再处理；你之前总表里 `up_limit` 的最大值有明显异常，这说明必须做显式质检。

---

# 六、目录与代码文件拆分方案

你要求代码写在 `src_data_domain_feature`。下面是最推荐的拆法。

## 目录结构

```text
src_data_domain_feature/
├── __init__.py
├── config.py
├── paths.py
├── registry.py
├── utils_io.py
├── utils_clean.py
├── utils_trade_calendar.py
├── build_domain_A_price_volume.py
├── build_domain_B_moneyflow.py
├── build_domain_C_chip.py
├── build_domain_D_fundamental.py
├── build_domain_E_intraday_summary.py
├── build_feature_registry.py
├── build_model_panel.py
└── run_all_domains.py
```

## 各文件职责

### `config.py`

统一配置：

* Raw 路径
* 输出路径
* epsilon
* 分位裁剪阈值
* 起始年份：
  * B 域：2010-01-01
  * C 域：2018-01-01
  * E 域：按分钟数据真实覆盖起始日

### `registry.py`

写死所有 feature 的元信息，最终导出成 `feature_registry.csv`。

### `utils_clean.py`

提供：

* 单位转换
* 分位裁剪
* 安全除法
* 日期格式标准化
* 缺口检查

### `build_domain_A_price_volume.py`

读 `daily.parquet` + `daily_basic.parquet`，构建 A 域。

### `build_domain_B_moneyflow.py`

读 `moneyflow.parquet` + `daily.parquet`，先统一金额单位，再构建 B 域。

### `build_domain_C_chip.py`

读 `cyq_perf.parquet` + `daily.parquet`，构建 C 域。

### `build_domain_D_fundamental.py`

读 `daily_basic.parquet` + 类别信息，构建 D 域模型字段。

### `build_domain_E_intraday_summary.py`

读 `stk_60_mins.parquet`，做日级聚合摘要。

### `build_model_panel.py`

按 `ts_code/trade_date` 横向合并 A/B/C/D/E，输出 `model_all_domains_daily.parquet`。

### `run_all_domains.py`

一键执行全流程。

---

# 七、最终产物清单

## `data/Feature_data/domain/`

* `domain_price_volume_daily.parquet`
* `domain_moneyflow_daily.parquet`
* `domain_chip_daily.parquet`
* `domain_fundamental_daily.parquet`
* `domain_intraday_1h_summary.parquet`

## `data/Feature_data/factor_ready/`

* `feature_A_price_volume.parquet`
* `feature_B_moneyflow.parquet`
* `feature_C_chip.parquet`
* `feature_E_intraday_summary.parquet`
* `feature_registry.csv`

## `data/Model_data/`

* `model_domain_D_fundamental.parquet`
* `model_all_domains_daily.parquet`

---

# 八、你的实际执行顺序

这是我最建议的推进顺序。

## 第一步

先做 `feature_registry.csv`，把 5 个域、全部最终字段、起始时间、是否喂 AlphaPROBE、是否喂模型一次性定死。

## 第二步

先完成 A/B/C 三个域。
因为这是你最核心、最有信息密度、最适合因子挖掘的部分。

## 第三步

做 E 域日内摘要。
只做 1h 摘要，不碰更高频原始 bar 融合。

## 第四步

做 D 域模型表。
这一步与 AlphaPROBE 解耦。

## 第五步

用 `build_model_panel.py` 合成总模型输入。

---

# 九、最后给你的明确判断

我把关键结论压成 6 句话：

1. **A/B/C/E 四个域进 AlphaPROBE，D 域不进。**
2. **所有进 AlphaPROBE 的域都不要再喂原始字段，只喂规范衍生字段。**
3. **量价域保留最基本的收益、振幅、影线、换手、量比，不要再把技术指标混进来。**
4. **资金流域必须做相对化，不允许直接用原始买卖额和手数。**
5. **筹码域必须把成本价转成“相对现价的位置与宽度”，不能直接拿成本原值去挖。**
6. **分钟数据只做 1h → 日级摘要，不做原始高频表达式挖掘。**

这套方案和你之前反复强调的思路是完全一致的：
**先把数据域做清楚，把搜索空间主动切小；在因子挖掘阶段保留可解释、低维、互补；在模型层再做跨域交互。**
