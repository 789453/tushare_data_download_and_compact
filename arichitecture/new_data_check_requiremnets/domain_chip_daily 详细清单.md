# 二、domain\_chip\_daily 详细清单

从统计上看，这个域最核心的问题不是缺失率，而是“位置/宽度类字段疑似被截尾或超界控制不足”，以及底层成本分位字段的质量没有被单独治理。比如 `close_vs_cost50` 的最小值、Q01 都是 -0.25，最大值、Q99 都是 0.6676；`close_vs_weight_avg` 同样边界贴合；`winner_rate` 最大到 100.62，`winner_rate_pct` 最大到 1.0062，说明至少存在上界超出理论定义域的问题。

## 1）原始基础字段清单

字段：\
`close`、`cost_5pct`、`cost_15pct`、`cost_50pct`、`cost_85pct`、`cost_95pct`、`weight_avg`、`winner_rate`、`his_low`、`his_high`

### 1.1 `close`

保留原值，不做任何截尾。\
只做基础合法性检查：

- `close > 0`
- 与日行情主表一致
- 若停牌，`close` 应可存在但需要与交易状态联动标记

### 1.2 `cost_5pct` \~ `cost_95pct`

这是整个 chip 域的根字段，必须首先治理。\
现状看这些字段约 2.96% 缺失，且部分最小值接近 0，`cost_50pct` 最小为 0，`cost_85pct/cost_95pct` 最小只有 0.2，这对真实股票价格来说虽然不一定绝对错，但很可能夹杂源表异常或历史极端样本。

必须新增以下校验：

- 单调性：`cost_5pct <= cost_15pct <= cost_50pct <= cost_85pct <= cost_95pct`
- 正值性：所有非缺失成本分位必须 `> 0`
- 与 `close` 的相对量级合理性：极端偏离时打质量标签，不直接裁掉
- 缺失联动：若任一关键成本分位缺失，则后续衍生字段应整体置空，不允许局部拼凑

建议新增状态字段：

- `chip_cost_monotonic_ok`
- `chip_cost_any_missing`
- `chip_cost_nonpositive_flag`

### 1.3 `weight_avg`

作为筹码平均成本，必须保证 `>0`。\
若 `weight_avg <= 0` 或缺失，不得参与任何位置类比值计算。\
不得 `fillna(0)`。

### 1.4 `winner_rate`

理论上应在 \[0,100]，但统计中最大到 100.62，说明存在上界溢出。\
这类字段不要简单 clip 到 100 然后结束，而应分两步：

- 原始值保留为 `winner_rate_raw`
- 若超过 \[0,100]，生成 `winner_rate_out_of_domain_flag=1`
- 产出供建模使用的 `winner_rate_capped = min(max(raw,0),100)`\
  这样既保留异常审计能力，也让下游有稳定值

### 1.5 `his_low`、`his_high`

必须检查：

- `his_low > 0`
- `his_high >= his_low`
- 若 `his_high == his_low`，则 `price_pos_hist` 不能计算，应置空并打 `hist_range_zero_flag`

***

## 2）衍生字段清单

字段：\
`close_vs_cost50`、`close_vs_weight_avg`、`chip_width_95_5`、`chip_width_85_15`、`overhang_95`、`support_5`、`winner_rate_pct`、`price_pos_hist`

### 2.1 `close_vs_cost50`

当前边界现象很强，说明大概率被裁切过。\
正确设计：

保留三层字段：

- `close_vs_cost50_raw = (close - cost_50pct) / cost_50pct`
- `close_vs_cost50_valid`：仅当 `cost_50pct > 0` 且底层质量通过时计算
- `close_vs_cost50_robust`：仅在建模层做温和稳健化，不得覆盖 raw

禁止动作：

- 禁止硬编码 clip 到固定区间
- 禁止在分母无效时返回 0

推荐动作：

- 若只用于树模型，可直接使用 raw + flag
- 若要供线性模型或标准化流水线使用，再派生 rank/logistic 版本

新增状态字段：

- `close_vs_cost50_den_invalid_flag`
- `close_vs_cost50_extreme_flag`

### 2.2 `close_vs_weight_avg`

和上面同理。\
由于当前最小值/最大值也与分位贴边，必须排查是否共享了统一 `winsorize_series`。\
不再做统一 clip。

### 2.3 `chip_width_95_5`、`chip_width_85_15`

这是宽度型状态量，尾部是有业务意义的，不应做分位截尾。\
重点检查：

- 分子分母定义是否一致
- 是否由错误排序产生负值
- 是否存在非单调成本导致的假宽度

建议：

- 保留 raw
- 对超大值只打 `chip_width_extreme_flag`
- 不做 clip，不做 fillna(0)

### 2.4 `overhang_95`、`support_5`

这类是位置/支撑压力类字段，本质上是状态信号。\
若底层筹码分位无效，应直接置空。\
若目前存在人为压边，必须取消。\
可加的标签：

- `overhang_95_outlier_flag`
- `support_5_outlier_flag`

### 2.5 `winner_rate_pct`

理论上应在 \[0,1]，但现在最大值 1.0062。\
这说明要么由 `winner_rate / 100` 直接换算而上游已超界，要么重复转换有误。\
处理方案：

- 保留 `winner_rate_pct_raw`
- 超界打标
- 供模型使用的稳定版再 clip 到 \[0,1]
- 同时回溯 `winner_rate` 生成链路

### 2.6 `price_pos_hist`

理论上在 \[0,1]，当前最值正好 0/1 且零值 6.20%，可能有大量边界样本，也可能有 `his_high == his_low` 或 `close <= his_low` / `close >= his_high` 情况。\
要做的不是裁切，而是区分原因：

- 若 `his_high == his_low`，结果置空，不是 0 或 1
- 若 close 真落在区间边缘，0/1 保留
- 新增 `hist_range_zero_flag`

