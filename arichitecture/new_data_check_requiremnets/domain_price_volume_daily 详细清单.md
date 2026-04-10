# 六、domain\_price\_volume\_daily 详细清单

这个域的问题很明确：收益率类被过度截尾，蜡烛图结构类有天然边界但不应再被误处理，成交量相关字段偏态很强但应该用映射而不是粗暴 clip。\
最关键证据是 `ret_cc_1d` 被截在 \[-0.0953, 0.1000]，且 Q01/Q99 与边界重合；`ret_oc_1d` 被截在 \[-0.5, 0.5]；`gap_open` 也在边界位置贴合。

## 1）原始价格字段

字段：\
`open`、`high`、`low`、`close`、`pre_close`

这些字段是根字段，不得做截尾。\
必须统一校验：

- `open, high, low, close, pre_close > 0`
- `high >= max(open, close, low)`
- `low <= min(open, close, high)`
- 对除权口径保持一致

***

## 2）成交与换手字段

字段：\
`turnover_rate_f`、`volume_ratio`、`turnover_free`、`volume_ratio_ln`

### 2.1 `turnover_rate_f`

最大值 5604.97，长尾极强。\
不建议原尺度 clip。\
推荐：

- 原值保留
- 建模派生 `log1p(turnover_rate_f)`
- 极端值打标
- 对于明显不可能值再回查源数据

### 2.2 `volume_ratio`

最大值 18459.21，Q99 仅 3.7。\
明显右尾厚。\
不要直接 winsorize 原值。\
因为你已经有 `volume_ratio_ln`，说明设计者本来也知道应做对数映射。\
建议：

- `volume_ratio_raw` 保留
- 模型主输入优先 `volume_ratio_ln`
- 对 `volume_ratio==0` 样本回查定义，若分母无效应置空而不是取 0

### 2.3 `turnover_free`

分布看起来相对稳定。\
保持原值即可，不建议额外截尾。

### 2.4 `volume_ratio_ln`

既然已对数化，就不需要再做 winsorize。\
只需确认是否由 `log1p` 正确生成，以及 0/缺失的上游处理是否合理。

***

## 3）收益率与跳空字段

字段：\
`ret_cc_1d`、`ret_oc_1d`、`gap_open`

### 3.1 `ret_cc_1d`

这是必须取消过度截尾的核心字段。\
当前最大 10%、最小约 -9.53%，且分位与边界重合。\
这会抹平制度差异与极端事件信号。

正确做法：

- 保留 `ret_cc_1d_raw = close / pre_close - 1`
- 不得统一 clip 到 1%/99% 或固定 ±10%
- 超出制度可解释范围很多的样本，只打 `ret_cc_1d_suspect_flag`
- 若建模需要稳健版本，再单独生成 `ret_cc_1d_robust`

### 3.2 `ret_oc_1d`

当前被压到 ±0.5。\
这个范围虽然比正常日涨跌大，但仍很像人为保护上限。\
必须回查是否存在统一 clip。\
同样采用 raw + robust + suspect\_flag 三层。

### 3.3 `gap_open`

当前 0 值 14.66%，边界也贴合。\
0 值可能是真实平开，也可能是开盘价回退错误。\
建议：

- 保留 0，但与涨跌停、停牌、复牌状态联检
- 不做额外截尾
- 对边界贴合样本回查是否被统一 winsorize

***

## 4）K线形态字段

字段：\
`intraday_range`、`upper_shadow_ratio`、`lower_shadow_ratio`

### 4.1 `intraday_range`

这是比例型振幅字段，统计看稳定。\
只做公式校验，不做截尾。

### 4.2 `upper_shadow_ratio` / `lower_shadow_ratio`

理论上多在 \[0,1]，当前最大值也到 1，零值分别 12.61% / 10.99%。\
这些 0 很可能是真实实体贴边日。\
不能把 0 当异常。\
只需检查是否超界，以及分母为 0 的特殊日如何处理。\
如果实体长度或全日振幅为 0，应置空而非硬算。

***

## 5）domain\_price\_volume\_daily 专项验证清单

1. `ret_cc_1d` 是否去掉 ±10% 截尾
2. `ret_oc_1d` 是否去掉 ±0.5 截尾
3. `gap_open` 尾部是否不再贴边
4. `volume_ratio` 是否改为 raw 保留 + ln 主用
5. K 线形态字段 0 值是否都能被业务解释
6. 重构后涨跌停、20cm、极端事件日是否能在图上真实出现

