# 五、domain\_moneyflow\_daily 详细清单

这个域的问题是最典型的“分母为 0、缺失、无成交、真实零值”混淆。\
统计上 `buy_elg_amount` 零值 36.25%，`sell_elg_amount` 零值 30.02%，`imb_elg_amt` 零值 27.84%，而 `imb_elg_amt` 的最小值、Q01、最大值、Q99 都顶在 -1/1。\
这说明你现在的逻辑里，至少存在“先算比值，再 fillna(0)”或“先补零再算”的问题。

## 1）金额原始字段

字段：\
`amount`、`buy_sm_amount`、`sell_sm_amount`、`buy_md_amount`、`sell_md_amount`、`buy_lg_amount`、`sell_lg_amount`、`buy_elg_amount`、`sell_elg_amount`、`net_mf_amount`

### 1.1 `amount`

这是所有归一化分母的总基准。\
必须规定：

- `amount <= 0` 时，所有相对额指标不得计算
- 新增 `amount_nonpositive_flag`
- `amount` 极小值样本不直接剔除，但要进入低流动性标签体系

### 1.2 各档买卖金额

小单/中单/大单/超大单的买卖金额都属于“非负金额原始事实”。\
原则：

- 原值保留
- 缺失不填 0
- 0 可以是真实 0，但要结合总成交额判断其语义\
  例如 `buy_elg_amount=0`，可能是真无超大单，也可能是上游缺失。\
  因此要新增每档：
- `*_missing_flag`
- `*_zero_flag`
- 与 `amount` 联动的 `*_no_activity_but_traded_flag`

### 1.3 `net_mf_amount`

缺失 4.89%，本身是净额，不宜直接补 0。\
应保留缺失，必要时增加“是否可计算”标签。

***

## 2）不平衡度字段

字段：\
`imb_sm_amt`、`imb_md_amt`、`imb_lg_amt`、`imb_elg_amt`

### 2.1 统一定义

若定义为 `(buy - sell) / (buy + sell)`，则必须统一如下：

- 当 `buy + sell == 0`：结果 NaN，不是 0
- 当 `buy + sell` 很小：结果可算但低置信度
- 当 `buy`、`sell` 任一缺失：结果 NaN，不得拿 0 顶

### 2.2 `imb_sm_amt` / `imb_md_amt`

当前零值率 2.34% / 2.40%，相对可接受，但仍需按统一框架改。\
保留边界值 ±1，因为它们可能是真实单边流。

### 2.3 `imb_lg_amt`

零值 2.82%，Q01 已到 -0.8568，说明右左尾都很重。\
不应裁切到更窄范围。\
只做可定义性控制和低成交打标。

### 2.4 `imb_elg_amt`

这是重点返工项。\
零值 27.84%，而分位与最值全部顶边。\
必须拆成：

- `imb_elg_amt_raw`
- `imb_elg_amt_valid`
- `imb_elg_amt_den_zero_flag`
- `imb_elg_amt_low_liq_flag`
- `imb_elg_amt_missing_input_flag`

禁止动作：

- 禁止 `fillna(0)` 后输出到最终表
- 禁止 clip 到 \[-1,1] 后就视为完成，因为公式本身已经天然在这个区间；你的问题不是范围太宽，而是无定义被伪装成合法边界或中性

***

## 3）相对量与份额字段

字段：\
`net_mf_to_amount`、`large_buy_share`、`large_sell_share`、`flow_divergence`

### 3.1 `net_mf_to_amount`

当前最值和分位贴边到 \[-0.4432, 0.3240]。\
这很像被截尾。\
正确做法：

- 原值保留
- 当 `amount <= 0` 或过小，置空或低置信度
- 不做硬剪
- 如担心极端尾部，可派生 robust 版本，不覆盖 raw

### 3.2 `large_buy_share` / `large_sell_share`

理论上在 \[0,1]。\
只做超界检查，不做 sigma。\
当总大单买卖额分母无效时应置空。\
0 与 1 都可能真实，不可当异常直接修正。

### 3.3 `flow_divergence`

当前范围是 \[-1,1]，零值 5.02%。\
需要回看公式。\
如果它本质是两个份额差或两个 imbalance 组合，那么也必须继承底层“无定义则 NaN”的规则。\
不能把所有无法定义的情况压成 0。

***

## 4）domain\_moneyflow\_daily 专项验证清单

1. `imb_elg_amt` 零值率应显著下降
2. 所有 `imb_*` 在 `buy+sell==0` 时是否返回 NaN
3. `net_mf_to_amount` 的边界贴合现象是否消失
4. 原始金额与衍生比值之间是否保持单调/方向一致
5. 低流动性股票是否被单独标记，而不是挤压进中性值
6. 抽样核查若干极值样本，确认是业务极值而不是分母爆炸

