下面这份文档，我按“**改造 AlphaPROBE 以适配你自己的 Tushare 特征域数据**”来写。目标不是讨论抽象原则，而是给出一套你可以真正落到工程里的方案。由于我无法看到你整个项目的全部源码，我不会假装知道所有类之间的精确调用链；但基于你上传的 `config.py`、`train_new_work.py`、`streamlit_app.py`、`feature_data_submit.json`、`feature_registry.csv` 以及市场分层文件 `index_daily_basic_circ_mv.json`，已经足够还原出**最合理、最稳、改动成本最低**的一套重构路径。

我先把结论放在最前面：

> 这次改造的核心，不是“改算子”，也不是“重写 AlphaPROBE”，而是把原来基于 Qlib `FeatureType` 的**单数据源表达式系统**，改造成一个“**分域数据集 + 域内变量表 + 域级训练入口 + 市场抽样器 + UI 配置器**”的体系。\
> 算子不动，搜索逻辑不动，知识池机制不动；真正要动的是：
>
> 1. 数据加载抽象
> 2. 特征注册与表达式变量映射
> 3. 训练入口参数化
> 4. INITIAL\_EXPR 热启动模板
> 5. 市场样本池抽样
> 6. Streamlit 的配置面板与实验管理

下面我会分成九个部分来讲：

1. 你现在手头数据与字段的“真实工程状态”
2. 当前 AlphaPROBE 依赖 Qlib 的地方到底在哪里
3. 如何把项目改造成“分域挖掘”
4. 四个域各自的变量、表达式空间与热启动策略
5. 市场样本筛选：200 股票池如何严谨抽样
6. 训练时间区间如何设计，分域是否共用池子
7. 具体需要修改哪些代码文件、怎么改
8. `streamlit_app.py` 如何适配
9. 最终你应该落成的目录、配置、运行方式与实验规范

***

# 一、先把你当前的数据状态读透：四个域已经具备“独立挖因子”的条件，但必须做域前质检

你现在已经非常清楚地把数据拆成了四个可挖掘域：

- `feature_A_price_volume`
- `feature_B_moneyflow`
- `feature_C_chip`
- `feature_E_intraday_summary`

这些信息已经被写进 `feature_data_submit.json`，其中每个域都只有 `ts_code`、`trade_date` 和 8 个衍生字段，正符合你之前设定的目标：**不再把原始字段喂给因子挖掘器，只喂无量纲、可解释的规范字段。**

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

## raw\_daily

你也明确说了：`raw_daily` 不是因子数据，但回测中可能需要用到。\
它包括 `open/high/low/close/pre_close/change/pct_chg/vol/amount`。\
这部分应该从“因子输入”里完全剥离，单独作为：

- 回测成交价格来源
- 交易约束判断来源
- 标签检查来源

这个边界必须保持清楚。

***

# 二、当前 AlphaPROBE 依赖 Qlib 的地方，真正要改的是“数据抽象层”而不是“因子逻辑层”

你给的 `config.py` 已经非常清楚地暴露了当前系统的假设。当前配置里：

- `FEATURES = [OPEN, CLOSE, HIGH, LOW, VOLUME, VWAP]`
- `OPERATORS` 是一套已经定义好的算子空间
- `DELTA_TIMES` 是滚动窗口集合
- `CONSTANTS` 是常数池。

同时 `train_new_work.py` 里训练入口直接实例化：

- `StockData(instrument=args.instruments, start_time=..., end_time=..., qlib_path=...)`
- 用 `Feature(FeatureType.CLOSE)` 构建目标：\
  \[\
  Ref(close, -20) / close - 1\
  ]
- 初始表达式 `INITIAL_EXPR` 也全部写死在 `$open/$close/$high/$low/$volume` 这套符号体系上。

所以你当前项目不是“某些地方用了 Qlib”，而是从**数据表示、变量名、目标定义、初始表达式到 UI 文案**都默认自己在处理 Qlib 风格 OHLCV。\
这也是为什么你这次必须做“分域适配”，而不能只改一个读取路径。

但好消息是：\
你明确说了**算子不改**，这其实让问题简单很多。\
因为整个表达式系统只要满足以下条件，就能继续跑：

1. 每个特征都有一个唯一的变量符号；
2. 表达式树节点能在底层数据矩阵上取到对应列；
3. 回测/评估端能对齐 `(stock, date)` 的因子值与标签。

所以你真正要改的不是算子系统，而是把“`FeatureType` 枚举 + Qlib StockData”替换成“**可由 parquet + registry 驱动的 GenericFeatureData**”。

***

# 三、改造目标：把 AlphaPROBE 变成“分域训练器”，而不是“一个大池子里混着跑”

你的要求非常明确：

- 四个域分别挖因子；
- 每个域使用自己的 8 个字段；
- 配置字段是不同的；
- 算子不变；
- 热启动表达式要重构；
- 增加市场样本筛选；
- Streamlit 需要适配。

这就意味着训练范式要从：

> 单一 `instruments + FEATURES + INITIAL_EXPR + StockData`

改成：

> `domain_name + domain_parquet + domain_feature_set + domain_initial_expr + sample_pool + generic_data_loader`

我建议你采用下面这个核心设计：

## 新的训练主入口参数

新增这些参数：

- `--data_mode`：`qlib` / `parquet_domain`
- `--domain`：`A_price_volume` / `B_moneyflow` / `C_chip` / `E_intraday`
- `--feature_path`
- `--raw_daily_path`
- `--feature_registry_path`
- `--sample_pool_path`
- `--sample_pool_size`
- `--sampling_mode`
- `--train_start`
- `--train_end`
- `--test_start`
- `--test_end`

然后把原来的 `--instruments csi300/sp500` 保留，但**降级为仅兼容旧模式**。\
对新模式，真正起作用的是：

- `domain`
- `feature_path`
- `sample_pool_path`

这样你就不会把“市场池”和“特征域”混成一件事。

***

# 四、四个域的表达式变量映射与热启动策略

这一部分非常关键。你说 `train_new_work.py` 中包含 `INITIAL_EXPR`，需要重构，但“相关热启动表达式我会在另一个任务再生成”。\
这句话的正确工程含义不是“这次先不管它”，而是：

> 这次要先把热启动表达式的**模板机制**改出来，让它能按域装载；至于具体表达式内容，可以后续再填。

也就是说，本次工程里应做的是：

- 从“一个全局 `INITIAL_EXPR` 列表”
- 改成“`DOMAIN_INITIAL_EXPR_MAP[domain]`”

## 1）变量符号系统必须重建

原来表达式写法是：

- `$open`
- `$close`
- `$high`
- `$low`
- `$volume`

现在应该改成支持任意 registry 中的字段名，比如：

- `$ret_cc_1d`
- `$turnover_free`
- `$imb_lg_amt`
- `$chip_width_95_5`
- `$hour1_ret`

这要求你在表达式解析器或特征工厂层新增一个“**字符串字段名 → 列索引**”映射，而不是依赖 `FeatureType.CLOSE` 这种固定枚举。

## 2）每个域都应该有自己的 VARIABLE LIST

我建议直接由 `feature_registry.csv` 自动生成。\
你现在 `feature_data_submit.json` 里已经给出了每个域的正式字段集合，这实际上就已经可以当做域变量清单的真值来源。

例如：

### A 域变量

- `$ret_cc_1d`
- `$ret_oc_1d`
- `$gap_open`
- `$intraday_range`
- `$upper_shadow_ratio`
- `$lower_shadow_ratio`
- `$turnover_free`
- `$volume_ratio_ln`

### B 域变量

- `$imb_sm_amt`
- `$imb_md_amt`
- `$imb_lg_amt`
- `$imb_elg_amt`
- `$net_mf_to_amount`
- `$large_buy_share`
- `$large_sell_share`
- `$flow_divergence`

### C 域变量

- `$close_vs_cost50`
- `$close_vs_weight_avg`
- `$chip_width_95_5`
- `$chip_width_85_15`
- `$overhang_95`
- `$support_5`
- `$winner_rate_pct`
- `$price_pos_hist`

### E 域变量

- `$hour1_ret`
- `$lasthour_ret`
- `$midday_reversal`
- `$intraday_trend_eff`
- `$hourly_volatility`
- `$volume_concentration_pm`
- `$vwap_close_bias_1h`
- `$high_low_time_skew`

## 3）INITIAL\_EXPR 不能再是跨域通用

原来的 `INITIAL_EXPR` 全是基于价格逻辑手写的，比如：

- `Div($high, $close)`
- `Div(Sub($high, $low), $open)`
- `TsStd($close, d) / $close`
- `TsMean($volume, d) / $volume` 等等。

这些表达式在新体系下不能复用。\
不是因为它们逻辑错，而是因为它们依赖的变量已经不存在。

这次工程文档里，你不需要立刻写出四个域的所有热启动表达式，但必须规定：

- 每个域都必须有一份自己的 `initial_expr_<domain>.json`
- 训练入口按域读取
- 如果该域没有热启动表达式，则退化为“空热启动”或“程序性生成简单一阶表达式”

这会让下一步你做 prompt 和热启动时非常顺。

***

# 五、市场样本筛选：200 股票池怎么选，才能既省成本又有市场代表性

这是你这次提问里最有研究价值的部分之一。你现在不想在全市场直接挖，因为数据量太大，希望每次只在 **200 个股票样本** 上挖。\
你提供了 `index_daily_basic_circ_mv.json`，其中至少包含：

- `l1_name`：一级行业
- `ts_code`
- `trade_date`
- `circ_mv`：流通市值

你希望基于：

- 一级行业 31 类
- 流通市值 `circ_mv`
- 可能对数化、可能不对数化
- 分成 3–4 组市值桶（微/小/中/大盘）

来做抽样。这个方向是对的，但你真正需要的是一套**分层、时间稳定、适合因子挖掘而不是适合组合投资**的采样方案。

***

## 先给结论：不要把不同市值完全分开挖，优先做“分层联合抽样”

你问过两个方向：

1. 不同市值股票分开挖因子？
2. 还是混在一起挖，但做分层抽样？

我的建议很明确：

> **当前阶段不要把大小盘完全分开挖。**\
> **优先用“行业 × 市值桶”的联合分层抽样，在同一个 200 股票池里挖。**

原因如下。

### 原因一：分开挖会让每个子池样本过小

你如果把 200 再拆成大中小盘三组，每组只剩几十只股票。\
对截面因子来说，这会让每日 IC 的横截面估计噪声显著变大，训练器会更容易围绕偶然结构做搜索。

### 原因二：很多因子不是“只在某一盘子有效”，而是“在不同盘子上表现强弱不同”

如果你一开始就分开挖，最后会得到四套高度局部化、迁移性很弱的因子库。\
这更适合策略细分阶段，不适合目前的“先建通用域内因子池”。

### 原因三：你真正稀缺的是算力和训练预算，不是子宇宙定义

所以最优策略通常是：

- 在一个**有代表性的联合样本池**里挖；
- 挖出来之后再看它对大中小盘的条件表现；
- 如果以后证明确实分盘效果显著，再考虑做盘子专属挖掘。

***

## 推荐的 200 股票池抽样方案：行业 × 市值桶 分层固定池

我建议采用如下逻辑。

### 第一步：确定抽样基准日

不要每天都重抽池。\
应该固定几个“样本池更新锚点”，例如：

- 每半年更新一次；
- 或每年更新一次。

理由是：\
因子挖掘阶段最怕“样本池本身不断变”，因为那会把训练不稳定性与市场非平稳性混在一起。

我建议你先用**年度固定池**：\
比如用每年 1 月第一个交易日的 `circ_mv + 一级行业` 做抽样。

### 第二步：市值变换

`circ_mv` 通常右偏，**建议先做对数**：

\[\
size = \log(1 + circ\_mv)\
]

你提到“不一定右偏”，这在局部年份可能如此，但从 A 股整体分布看，流通市值做 log 基本总是更稳健。\
即便不是极端右偏，log 也能让桶划分更平滑。

### 第三步：按年度全市场做 4 桶

我建议先做 **4 桶** 而不是 3 桶：

- 微盘 / 小盘 / 中盘 / 大盘

理由是：

- 3 桶时“微小盘”常被混在一起，行为差异太大；
- 4 桶在 200 样本里仍然够用；
- 以后你要分析条件表现时也更细。

### 第四步：行业 × 市值桶 联合配额

你有一级行业 31 个。\
200 股票不可能让 31×4 的所有格子都满，但可以采用以下原则：

1. 先按行业在全市场的股票数占比给基础配额；
2. 再在行业内部按市值桶比例切分；
3. 每个行业至少保留 2–3 只；
4. 如果某行业股票太少，则最小保留 1 只；
5. 总数控制在 200。

这样会得到一个**代表整个市场结构**而又不至于被单一大行业垄断的池子。

### 第五步：股票池在年度内固定

例如 2020 全年用同一组 200 只，2021 重新抽一次。\
这样你的训练集是由“年份池”拼接起来，而不是每天都漂移。

***

## 时间上怎么保证区间长度与市场代表性？

你的问题非常好：

> 时间上怎么确保有一定长度的区间，每个因子所在的股票池要不同吗？

我的建议是：

### 1）因子所在股票池不要因因子而不同

也就是说，同一个域的一轮训练里，所有候选表达式都应该在同一个样本池上评估。\
不能“一个因子一套股票池”，那会让比较失去意义。

### 2）训练集至少覆盖多个市场状态

如果你做年度固定池，那么训练区间至少应包含：

- 上涨段
- 下跌段
- 震荡段

从工程上讲，最简单的做法是训练期至少 **4–6 年**，而不是 1–2 年。\
对于不同域：

- A 域可用全历史；
- B 域从 2010 起；
- C 域从 2018 起；
- E 域取分钟数据真实覆盖期。

### 3）训练池与测试池可以共用抽样逻辑，但不共用具体日期

例如：

- 训练：2014–2020
- 测试：2022–2025

这个思路其实和你原来的 `train_new_work.py` 是一致的：它已经把训练与测试分成两个 `StockData` 区间了。\
你只需要把这个区间逻辑迁移到自定义数据加载器上。

***

# 六、数据加载层应该怎么改：从 Qlib `StockData` 改成 `GenericDomainData`

这是整个项目里最核心的代码改造点。

## 你现在的隐含抽象

现在 `train_new_work.py` 假设：

- `StockData` 能根据 `instrument/start/end/qlib_path` 读出一个标准特征矩阵；
- `Feature(FeatureType.CLOSE)` 这样的表达式叶子能映射到底层数据；
- target 可以用 `Ref(close, -20)/close-1` 来定义。

## 你需要的新抽象

我建议新增一个类，例如：

- `GenericDomainData`
- 或 `ParquetDomainData`

它负责：

1. 读取某个 `feature_<domain>.parquet`
2. 根据 `sample_pool` 过滤股票集合
3. 根据 `start/end` 过滤日期
4. 把 `(ts_code, trade_date)` 面板转成内部表达式评估器可消费的 tensor / matrix
5. 提供变量名到列索引的映射
6. 可选读取 `raw_daily.parquet` 用于 target 或测试回测对齐

## 这个类至少要暴露的能力

- `feature_names`
- `stock_ids`
- `dates`
- `get_feature_tensor(name)`
- `make_target(label_days, raw_daily_path)`
- `clip_and_mask_by_domain(domain)`

这里最后一个方法很重要。因为前面已经看到了 A/C/E 域存在异常极值，所以**每个域都应有一套 domain-specific quality filter**。\
例如：

- A 域：`ret_cc_1d/gap_open/intraday_range` 做分位裁剪
- C 域：`price_pos_hist/overhang_95/chip_width_*` 做上尾裁剪
- E 域：`intraday_trend_eff` 做强裁剪。

注意，这不是改算子，而是改底层数据质量控制。

***

# 七、训练入口 `train_new_work.py` 应该怎样重构

这个文件是这次改造的主要入口。当前它的几个关键结构如下：

- 读取环境变量里的 `QLIB_PATH`
- 直接实例化 `StockData`
- target 固定为未来 20 日收益
- `INITIAL_EXPR` 是全局常量
- 没有域概念
- 没有样本池概念。

我建议改成下面这个结构。

***

## 1）保留旧模式，新增新模式

不要一次性删掉 Qlib 路径，最稳妥做法是：

- `--data_mode qlib`
- `--data_mode parquet_domain`

这样原先逻辑仍然可跑，便于回退和对照实验。

***

## 2）新增域配置解析

增加一个函数：

- `build_domain_config(args.domain, args.feature_registry_path)`

输出内容：

- 域特征列表
- 域数据路径
- 域热启动表达式路径
- 域质量裁剪规则
- 域默认训练区间

***

## 3）替换 `FEATURES`

旧的 `FEATURES = [FeatureType.OPEN, ...]` 应该只在旧模式里有效。

新模式里应该由 parquet 中的列名驱动，而不是写死枚举。

***

## 4）target 生成逻辑重写

你现在的 target 是：\
\[\
Ref(close, -20) / close - 1\
]\
这在 Qlib 模式下没问题，因为 `close` 是表达式变量。

新模式下建议不要再从 feature 域里定义 target，而是统一从 `raw_daily.parquet` 生成未来收益标签。\
也就是：

- 训练输入来自 `feature_A/B/C/E`
- 标签来自 `raw_daily.close`

这样你可以保证四个域的标签一致，不会因为域不同而 target 口径变。

***

## 5）INITIAL\_EXPR 改成域级装载

从：

- `INITIAL_EXPR = [...]`

改成：

- `INITIAL_EXPR = load_initial_expr(domain=args.domain)`

如果文件不存在：

- fallback 到空列表
- 或自动生成简单一阶模板，例如：
  - `TsMean($feature, d)`
  - `TsStd($feature, d)`
  - `TsRank($feature, d)`
  - `TsDelta($feature, d)`

这一步非常必要，因为你已经明确说后续会单独做热启动表达式任务。

***

## 6）加入 sample pool

新增一层股票过滤：

- 先从 `sample_pool_path` 读出训练股票列表
- `GenericDomainData` 只加载这些股票

这一步就是把“全市场挖因子”改成“代表性样本池挖因子”的关键。

***

# 八、`config.py` 怎么改：不再是单一 FEATURES 配置，而是域模板注册

现在的 `config.py` 本质上同时承担了三件事：

1. 算子集合
2. 变量集合
3. 时间窗口 / 常数池。

你现在明确说了：**算子不改，不需要调整。**\
所以建议做的是：

## 保留不动的部分

- `OPERATORS`
- `DELTA_TIMES`
- `CONSTANTS`
- GFN 超参数

## 改掉的部分

把：

```
FEATURES = [
    FeatureType.OPEN,
    FeatureType.CLOSE,
    FeatureType.HIGH,
    FeatureType.LOW,
    FeatureType.VOLUME,
    FeatureType.VWAP
]

```

改成：

- `DOMAIN_FEATURES = {...}`
- 或者根本不在 `config.py` 写死，改为运行时加载 registry

这是更推荐的方案。因为你未来很可能还会加 F 域、G 域。\
如果 `config.py` 每次都要改，就说明抽象还没立稳。

***

# 九、`streamlit_app.py` 应该怎么改：让 UI 从“Qlib 训练面板”变成“域配置实验面板”

你上传的 `streamlit_app.py` 现在默认自己在控制一个：

- `src/train_new_work.py`
- 参数里重点是 `instruments = csi300 / sp500`
- 训练模式是新开/继续
- 没有域概念、没有 feature path、没有 sample pool 配置。

这对旧版没问题，但对你新体系不够。

我建议 UI 改造分成四块。

***

## 1）增加“数据模式”

在侧边栏新增：

- 数据模式：`Qlib` / `Parquet Domain`

如果选 `Qlib`，保留旧逻辑；\
如果选 `Parquet Domain`，显示新表单。

***

## 2）新增“域选择”

当 `Parquet Domain` 模式下，新增：

- 域选择：
  - A\_price\_volume
  - B\_moneyflow
  - C\_chip
  - E\_intraday\_summary

然后根据域自动带出：

- 默认 feature parquet 路径
- 默认训练区间
- 默认热启动模板路径

***

## 3）新增“样本池设置”

在 UI 里增加：

- `sample_pool_mode`
  - full\_market
  - stratified\_200
  - custom\_list
- `sample_pool_size`
- `rebalance_freq`
  - yearly
  - half\_yearly

并支持查看：

- 当前样本池行业分布
- 当前样本池市值桶分布

这样你就不会在每次训练时忘了“这轮到底用的是哪个样本池”。

***

## 4）监控页增加“域信息”

实验列表里不应该只显示 run id，而应该显示：

- domain
- data\_mode
- sample\_pool\_mode
- sample\_pool\_size
- train/test range

否则后面实验一多，你会很难区分。

***

# 十、你这次最应该形成的项目目录结构

我建议你把 AlphaPROBE 项目扩成下面这个结构：

```
project/
├── data/
│   ├── Raw_data/
│   │   └── daily.parquet
│   ├── Feature_data/
│   │   ├── factor_ready/
│   │   │   ├── feature_A_price_volume.parquet
│   │   │   ├── feature_B_moneyflow.parquet
│   │   │   ├── feature_C_chip.parquet
│   │   │   ├── feature_E_intraday_summary.parquet
│   │   │   └── feature_registry.csv
│   ├── sample_pools/
│   │   ├── pool_stratified_200_2020.json
│   │   ├── pool_stratified_200_2021.json
│   │   └── ...
│   └── knowledge_logs/
├── src/
│   ├── train_new_work.py
│   ├── data_adapters/
│   │   ├── generic_domain_data.py
│   │   ├── feature_registry_loader.py
│   │   └── sample_pool_loader.py
│   ├── domain_configs/
│   │   ├── domain_A.py
│   │   ├── domain_B.py
│   │   ├── domain_C.py
│   │   └── domain_E.py
│   ├── initial_expr/
│   │   ├── initial_expr_A.json
│   │   ├── initial_expr_B.json
│   │   ├── initial_expr_C.json
│   │   └── initial_expr_E.json
│   └── utils/
├── streamlit_app.py
└── config.py

```

这样以后你要加新域，根本不用动主训练逻辑，只需要：

1. 增加 parquet
2. 增加 registry
3. 增加 domain config
4. 增加 initial expr

***

# 十一、最推荐的训练策略：先分域单独挖，再做后验组合，不要一上来跨域混挖

你这次的分域思路是非常对的。\
基于当前数据情况，我建议训练顺序是：

## 第一优先级：A 域

原因：

- 历史长
- 字段语义稳定
- 最接近原来 Qlib 体系
- 最容易先把整个新数据管线跑通。

## 第二优先级：B 域

原因：

- 2010 起覆盖较长
- 字段规范化程度高
- 对 A 域形成很好的行为补充。

## 第三优先级：C 域

原因：

- 经济意义强
- 但异常值处理最重要
- 起始年份较短。

## 第四优先级：E 域

原因：

- 时间最短
- 统计上最容易受噪音影响
- `intraday_trend_eff` 需要先做强治理。

这四个域都应该独立形成自己的知识池、日志目录、结果池文件。\
**不要在当前阶段做跨域混挖。**

***

# 十二、最后给你一份“最小可执行改造路线图”

如果你想最低风险把工程改起来，我建议严格按这个顺序：

## 第 1 步：把 `config.py` 的 FEATURES 依赖解除

目标：让项目不再强依赖 `FeatureType.OPEN/CLOSE/...`。

## 第 2 步：新增 `GenericDomainData`

目标：读 parquet + registry + sample pool，替代 Qlib `StockData`。

## 第 3 步：改 `train_new_work.py`

目标：新增 `data_mode/domain/feature_path/raw_daily_path/sample_pool_path`，并按域加载 `INITIAL_EXPR`。

## 第 4 步：实现样本池构造器

目标：用 `index_daily_basic_circ_mv.json` 做年度固定的 200 股票分层样本池。

## 第 5 步：改 `streamlit_app.py`

目标：支持域选择、数据模式、样本池模式、域级实验监控。

## 第 6 步：最后再做热启动表达式内容

目标：此时基础设施已经稳了，你再单独针对 A/B/C/E 写 prompt 与 initial expr，成本最低。

***

# 十三、我对你当前方案的最终评价

我把最重要的评价说得直接一点：

你现在的思路，已经不是“我想试试看把自己的数据塞进去”，而是在做一件更成熟的事：

> **把 AlphaPROBE 从一个“依赖固定 OHLCV 数据源的因子搜索器”，改造成一个“能够面向你自己构造的数据域做搜索的研究平台”。**

这件事真正难的不是算子，而是工程边界。\
而你现在已经把几个最重要的边界想对了：

- 因子挖掘与模型融合分离
- 分域优先于混域
- 原始 daily 只做回测/标签，不做因子输入
- 200 股票抽样优先于全市场暴力训练
- 热启动按域定制而不是全局共用
- Streamlit 需要跟随训练范式一起升级。

如果要再压成一句最实用的建议，那就是：

> **先把“分域数据加载 + 样本池抽样 + 域级训练入口”打通，再去做热启动和提示词；不要反过来。**

因为只要这三层没立住，你后面无论 prompt 写得多漂亮、initial expr 多聪明，都会被底层数据抽象拖住。

你下一步最值得做的是两件事中的一个：\
第一，我可以继续给你写一份**“代码级修改清单”**，按文件逐条列出 `train_new_work.py / config.py / streamlit_app.py` 分别该新增哪些函数、参数和类；\
第二，我可以直接帮你把**“200 股票分层抽样器”** 的规则和伪代码完整写出来。
