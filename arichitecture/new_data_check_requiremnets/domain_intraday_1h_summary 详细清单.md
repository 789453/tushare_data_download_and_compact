# 四、domain\_intraday\_1h\_summary 详细清单

这是当前最需要优先重构的域。因为这里暴露的不是“数据有点偏”，而是“很可能窗口定义、聚合或 fallback 逻辑本身错了”。最典型证据是 `hour1_ret` 零值 85.03%，同时 `hour1_open` 和 `hour1_close` 的统计几乎一致；`intraday_trend_eff` 被硬截到 ±20；`vwap_close_bias_1h` 均值与 1%/99% 位置非常可疑。

## 1）日级基准字段

字段：\
`open_day`、`close_day`、`high_day`、`low_day`、`vol_total`、`amount_total`

### 1.1 价格字段

这些字段若来自日行情主表，应保持与日表一致。\
当前 `open_day/close_day/high_day/low_day` 仍有约 0.43%-0.46% 的零值。\
对股票日价而言，0 通常不是合法价格，应该解释为：

- 停牌占位
- 回补失败
- join 缺失默认 0\
  因此这里必须禁止 0 价格直接参与衍生计算。

建议新增：

- `day_price_nonpositive_flag`
- 若任一核心价格 <=0，相关 intraday 衍生列全部置空

### 1.2 `vol_total`、`amount_total`

零值约 3.17%。\
这可能是真停牌/无交易，也可能是聚合失败。\
必须区分：

- `no_trade_day_flag`
- `missing_intraday_source_flag`

***

## 2）聚合统计字段

字段：\
`sum_abs_ret`、`hourly_volatility`、`count`

### 2.1 `sum_abs_ret`

零值 3.66%，如果 `count` 很低，这可能合理。\
但如果 `count` 正常却 `sum_abs_ret=0`，说明分钟收益被压平。\
要加联合验证：

- 若 `count >= min_bar_count` 且 `sum_abs_ret == 0`，打异常标签

### 2.2 `hourly_volatility`

零值 3.22%，需与 `count` 和 `sum_abs_ret` 联检。\
不能简单填 0。\
当有效 bar 数不足时应置空。

### 2.3 `count`

这是质量控制核心字段。\
以后所有 intraday 衍生列必须依赖 `count` 判断可算性。\
建议规定：

- `count < hard_min_count`：相关统计一律 NaN
- `hard_min_count <= count < soft_min_count`：可算但低置信度打标\
  这是避免“只有一根 bar 却算出稳定收益”的关键。

***

## 3）第一小时/最后一小时价格字段

字段：\
`hour1_open`、`hour1_close`、`lasthour_open`、`lasthour_close`

### 3.1 `hour1_open` / `hour1_close`

当前两者统计几乎完全相同，是 `hour1_ret` 高零值的直接旁证。\
必须回炉重算，不能在现有结果上再补丁。

明确规范：

- 第一小时窗口定义要固定到交易制度
- `hour1_open` 取窗口首笔有效成交
- `hour1_close` 取窗口末笔有效成交
- 若窗口无成交：两者都 NaN，`hour1_has_trade=0`
- 若仅一笔成交：允许收益 0，但必须 `hour1_single_trade_flag=1`

### 3.2 `lasthour_open` / `lasthour_close`

最后一小时相对正常，但仍要执行同样规则。\
注意如果尾盘存在集合竞价或早收市等特殊制度，窗口必须制度化定义。

***

## 4）关键衍生字段

字段：\
`hour1_ret`、`lasthour_ret`、`midday_reversal`、`intraday_trend_eff`、`volume_concentration_pm`、`vwap_close_bias_1h`、`high_low_time_skew`、`high_time_idx`、`low_time_idx`

### 4.1 `hour1_ret`

必须作为专项 Bug 修复项。\
85.03% 零值绝不是正常分布。

必须改成：

- `hour1_ret_raw` 仅在 `hour1_open > 0 and hour1_close > 0 and hour1_has_trade=1` 时计算
- 无交易不返回 0
- 单笔交易可返回 0，但需标签
- 低 bar 数样本加 `hour1_low_count_flag`

验收目标：

- 零值比例显著下降
- 零值样本大多能解释为单笔/停牌/无交易，而不是默认取同一笔

### 4.2 `lasthour_ret`

虽然零值只有 12.25%，但最大值 2.3477 很夸张。\
这可能来自尾盘价格近 0、复权错位、分母错取。\
必须检查：

- 分母是否总是 `lasthour_open`
- 是否有前复权/不复权口径混用
- 是否存在 `lasthour_open` 极小或错误值

### 4.3 `midday_reversal`

范围与分位非常对称贴边，当前看像派生自两个已经被限制过的收益率。\
建议：

- 先重算上游 `hour1_ret`、`lasthour_ret`
- 再重做 `midday_reversal`
- 不做单独 clip

### 4.4 `intraday_trend_eff`

最值直接卡在 -20 / 20，Q01/Q99 也恰好是 -20 / 20，几乎可以确认被硬截尾。\
必须取消硬编码 clip。\
建议：

- 保留 raw
- 若担心极端分母导致爆炸，则做分母下限校验
- 若仍需模型稳健版本，另派生 `intraday_trend_eff_robust`

### 4.5 `volume_concentration_pm`

理论上在 \[0,1]，当前分位合理。\
这里不要再做 sigma。\
重点在于：

- 当 `vol_total == 0` 时应为 NaN，不是 0
- 当 `vol_pm` 缺失时不可直接按 0 算

### 4.6 `vwap_close_bias_1h`

当前最小值 -0.9999，均值 -0.8979，Q01/Q99 也几乎都在 -0.9 附近，这明显不正常。\
这类分布说明非常可能：

- 公式写反
- 除法基准取错
- 缺失/无交易时回退到固定值
- 窗口 VWAP 几乎始终缺失，被某个默认值替代\
  这必须单列为 P0 级返工，不是简单清洗能解决的。\
  建议先回看定义，重新推公式。若是 `(close - vwap1h)/vwap1h`，均值不应长期接近 -0.9。

### 4.7 `high_low_time_skew`

理论在 \[-1,1] 没问题，但当前零值 20.73%，且最值、Q01/Q99 又顶在 -1/1。\
要区分：

- 真正极值
- 高低点出现在同一时刻或无效时刻
- bar 数不足\
  不能直接当普通连续变量处理。

### 4.8 `high_time_idx` / `low_time_idx`

这两个字段不是连续数值特征，而是位置索引特征。\
不能再做数值化截尾。\
应进一步派生为：

- 归一化位置 `idx_norm = idx / max_count`
- 早盘/午盘/尾盘桶化特征\
  这样更适合模型。

***

## 5）domain\_intraday\_1h\_summary 专项验证清单

1. `hour1_ret` 零值率是否显著下降
2. `hour1_open != hour1_close` 的比例是否回到合理水平
3. `intraday_trend_eff` 是否去除 ±20 人工边界
4. `vwap_close_bias_1h` 分布是否恢复到接近 0 中心而非 -0.9 常数带
5. 所有 intraday 衍生列在 `count` 过低时是否统一置空
6. 随机抽取 100 条样本回放分钟线，人工核对公式正确性

***

#
