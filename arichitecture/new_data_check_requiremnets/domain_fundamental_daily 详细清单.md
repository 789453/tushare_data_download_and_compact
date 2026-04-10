# 三、domain\_fundamental\_daily 详细清单

这个域的本质不是“清洗不够”，而是“经济语义和统计空间不匹配”。\
`pe_ttm` 最大 2,653,832，Q99 只有 1047；`ps_ttm` 最大 6,318,763,008，Q99 只有 57.6979；`dv_ttm` 缺失 34.98%。这说明极端偏态和高缺失是这里的核心矛盾。

## 1）原始估值字段清单

字段：\
`pe_ttm`、`pb`、`ps_ttm`、`dv_ttm`

### 1.1 `pe_ttm`

17.17% 缺失，右尾极长。\
处理原则：

- 不在原尺度做统一截尾
- 原值保留
- 缺失不填 0
- 对极端大值不直接判坏值，先视为“经济上可疑但不一定错误”

推荐派生：

- `pe_ttm_valid_flag`
- `pe_ttm_log = log1p(pe_ttm)`，仅限正值
- `pe_ttm_rank_ind` 已存在，可以继续保留
- 如需更稳健，新增 `pe_ttm_rank_mkt`

### 1.2 `pb`

缺失低于 2%，但最大值 45723 非常大。\
同样不在原尺度截尾。\
推荐：

- 原值保留
- 建模使用 `log1p(pb)` 或 rank
- 极端右尾只打 flag

### 1.3 `ps_ttm`

这是问题最严重的偏态字段之一。平均值 37694 但 Q99 才 57.6979，说明均值已被极少数极端值完全拖飞。\
这里不应再讨论 3sigma。\
建议：

- 绝不直接标准化原值
- 原值留档
- 模型输入优先使用 `log1p(ps_ttm)` 和行业内分位 rank
- 对极端异常公司，可额外生成 `ps_ttm_super_extreme_flag`

### 1.4 `dv_ttm`

缺失 34.98%，这是结构性高缺失字段。\
必须拆成三层：

- `dv_ttm_raw`
- `dv_ttm_missing_flag`
- `dv_ttm_zero_flag`

不能做的事：

- 不能直接中位数填充
- 不能把缺失当 0 分红
- 不能只保留 rank 而丢掉原值语义

如果业务允许，还应区分：

- 真正无分红
- 财报口径暂缺
- 上市时间不足
- 数据源缺失

***

## 2）规模和结构字段清单

字段：\
`total_share`、`free_share`、`total_mv`、`circ_mv`、`free_float_ratio`、`circ_mv_to_total_mv`

### 2.1 `total_share`、`free_share`、`total_mv`、`circ_mv`

这些字段相对稳定，缺失率低。\
处理建议：

- 原值保留
- 建模可用 log1p 映射
- 做一致性检查：
  - `free_share <= total_share`
  - `circ_mv <= total_mv * 容差`\
    当前 `circ_mv_to_total_mv` 最大值达到 1.0035，说明已有轻微超界。\
    这通常来自数据同步误差或口径不齐，不能忽略。

### 2.2 `free_float_ratio`

理论范围 \[0,1]。\
只做超界检查，不做 sigma。\
若超界，保留 raw + capped 双版本。

### 2.3 `circ_mv_to_total_mv`

理论上应在 (0,1]，当前最大 1.0035。\
必须新增：

- `circ_mv_to_total_mv_raw`
- `circ_mv_to_total_mv_out_of_domain_flag`
- `circ_mv_to_total_mv_capped`

***

## 3）排序与评分字段清单

字段：\
`pe_ttm_rank_ind`、`pb_rank_ind`、`ps_ttm_rank_ind`、`dv_ttm_rank_mkt`、`mv_rank_mkt`、`valuation_compress_score`

### 3.1 各类 `rank`

排序字段天生稳健，不需要再做 winsorize。\
注意：rank 的缺失应继承原值缺失，而不是补中位数。\
例如 `pe_ttm_rank_ind` 缺失 17.17%，`dv_ttm_rank_mkt` 缺失 34.98%。\
建议保留缺失，让模型或后续策略自行使用 missing split。

### 3.2 `valuation_compress_score`

该字段完全落在负区间 \[-0.9998, -0.0004]。\
这不一定错，但必须明确定义：

- 如果它就是“压缩程度的负向评分”，那不要再做对称标准化
- 如果理论上应是双边分布，那么就说明公式设计有问题\
  必须在工程文档中写清楚字段解释，否则后续研究者会误判为异常值

***

## 4）domain\_fundamental\_daily 专项验证清单

1. 检查估值类极端值是否由分母极小导致
2. 检查 `circ_mv_to_total_mv > 1` 的比例与来源
3. 检查 `dv_ttm` 缺失是否集中在特定行业/上市阶段
4. 评估 raw / log / rank 三种输入方式的稳定性
5. 验证重构后均值不再被少数极端值主导
6. 确认任何缺失都未被错误替换成 0

