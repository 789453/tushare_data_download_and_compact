A股日度与季度基本面因子体系设计、工程实现与测试方案

一、任务边界与现状说明

本报告面向“全A股、日度 daily_basic + 日线行情 + 季度 fina_indicator + 申万 1~3 级行业”的统一因子研究框架设计。当前会话中可确认的数据包括：申万行业映射样例与字段说明、daily_basic 字段说明、daily 行情字段说明，以及 Tushare 的 daily_basic / fina_indicator 接口字段列表。其中，申万行业映射采用 index_member_all.json，记录 l1/l2/l3 行业代码与名称、股票代码、入选日期和退出日期，可用于按交易日做点时行业归属。uploaded 文件显示 daily 与 daily_basic 的真实数据范围覆盖 2005-01-04 至 2026-03-13，股票池为全 A 股。需要特别说明的是，本会话运行环境未挂载你指定的 Windows 本地路径 D:\Trading\data_ever_26_3_14\data\Raw_data\daily.parquet，也未暴露 TUSHARE_TOKEN，因此我无法在本会话中直接生成真实的 IC、分组收益和绩效数值；但我已经按你的要求给出可直接在本机执行的完整工程脚本与文档设计，脚本会自动读取你本地 parquet、根据环境变量下载季度财务、按行业与中性化方式构建因子，并输出测试结果。

二、设计原则：为什么一定要优先采用比率、无量纲、相对量

A股横截面因子要想长期可用，最关键的是“可比较”。直接使用利润、市值、股本、营收等原始量纲变量，在不同行业、不同规模和不同时期之间都不可比，因此核心原则是尽量转成比率、无量纲、增长率、分位数、相对行业位置、滚动标准分、相对自身历史位置等。具体有四个层次。

第一层是“经济含义稳定”的原始比率，如 EP=1/PE_TTM、BP=1/PB、SP=1/PS_TTM、股息率、流动比率、速动比率、ROE、ROIC、OCF/Revenue、Debt/Assets 等，这些变量天然具备横向比较意义。

第二层是“相对变化”算子，包括滞后、差分、同比、环比、滚动变化率、加速度、斜率。比如 turnover_rate_f 的 5 日变化率衡量资金关注边际变化；pb 的 20 日变动反映估值压缩或扩张；q_ocf_to_sales 的同比改善比其静态水平更能解释质量重估。

第三层是“横截面位置”算子，即分位数、桶、分组、行业内排序。一个 1.8 倍 PB 的银行与一个 1.8 倍 PB 的半导体公司几乎没有同样经济含义，因此必须转成行业内分位数、行业内 z-score 或行业中性残差。行业比较是本任务中最重要的工程环节之一。

第四层是“风险净化”算子，即中性化、正交化、尾部截断与稳健标准化。A股中市值、流动性、行业暴露会污染大部分基本面因子，因此正式研究用信号必须至少提供：全市场版本、行业内版本、行业+规模中性版本三套结果进行对照。

三、数据层设计

1. 日度行情 raw_daily
建议保留 open/high/low/close/pre_close/vol/amount，并派生 ret_1、ret_5、ret_20、ret_60、振幅、实体占比、换手近似、成交额趋势、波动率、偏度、上下影线强弱、量价协同等交易性特征。虽然用户重点是基本面与 daily_basic，但 raw_daily 是未来收益计算、停牌过滤、涨跌停过滤、成交约束、分组回测不可缺少的数据层。

2. 日度基本面 raw_daily_basic
这是日频因子构建的主战场。原始字段中最关键的是 pe/pe_ttm/pb/ps/ps_ttm/dv_ratio/dv_ttm/turnover_rate/turnover_rate_f/volume_ratio/total_mv/circ_mv/free_share/circ_mv 等。它们不应被直接使用，而应经过倒数、对数、行业分位、历史分位、变化率、滚动标准化、桶化等处理。

3. 季度财务 fina_indicator
fina_indicator 的字段很多，但并非越多越好。建议围绕估值支持、盈利质量、资本效率、营运效率、杠杆偿债、现金流质量、边际改善七大类精选高质量指标。季度数据必须按照 ann_date 对未来交易日生效，严禁直接按 end_date 前视；在日频研究中，需要以 ann_date 为生效起点 forward fill 到下次公告前一天。

4. 行业层 index_member_all.json
行业文件记录 l1/l2/l3 三层分类和 in_date/out_date。工程上不能只拿一个“当前行业”去回填历史，否则会产生严重样本穿越。必须按 trade_date 判断 trade_date>=in_date 且 (out_date 为空或 trade_date<out_date) 才视为当日有效行业。然后在 l1/l2/l3 三层都生成行业编码，供不同粒度的行业比较和中性化使用。一般建议：
- 宽行业轮动较强时，先做 l1 行业中性；
- 细分产业链估值差异显著时，用 l2/l3 行业内排序；
- 当 l3 样本太少时回退到 l2，再回退到 l1。

四、日度因子设计：以 daily_basic 为核心，加入“滞后 + 分位 + 变化率”

（一）估值类因子
1. Earning Yield：ep_ttm = 1 / pe_ttm
比直接 PE 更稳定；亏损股设为空。进一步构造：
- ep_ttm_lag1、lag5、lag20
- ep_ttm_chg20 = ep_ttm / lag20 - 1
- ep_ttm_rank_cs：全市场横截面分位
- ep_ttm_rank_ind_l1/l2/l3：行业内分位
- ep_ttm_hist_pct252：个股过去 252 日自身历史分位
- ep_ttm_neu：行业+ln(circ_mv) 中性残差

2. Book Yield：bp = 1 / pb
适合作为资产重估因子，尤其对周期、金融、地产更有意义。建议与 ROE 或 q_roe 联合使用，构造“高 BP 且高 ROE”的价值质量复合因子，避免陷入价值陷阱。

3. Sales Yield：sp_ttm = 1 / ps_ttm
对尚未稳定盈利、但收入规模有效的公司比 PE 更稳健。可以配合 gross_margin 或 q_profit_to_gr 做“高销售收益+利润率改善”。

4. Dividend Yield：div_ttm = dv_ttm / 100
在 A 股中更适合做防御或低波价值增强，建议做行业内分位而非绝对值比较。

（二）流动性 / 关注度 / 拥挤度类因子
1. turn_f = log1p(turnover_rate_f)
2. vol_ratio = log1p(volume_ratio)
3. size = log(circ_mv)
4. ff_ratio = free_share / float_share

派生建议：
- turn_f_ma5, turn_f_ma20, turn_f_z20
- turn_f_chg5 = turn_f / lag5 - 1
- volume_ratio_rank_ind_l2
- crowding = z(turn_f,20) + z(vol_ratio,20)
- anti_crowding = - crowding
- liq_shock = turn_f / ma20(turn_f) - 1

这些因子适合做短中期择时型横截面解释，但容易与动量、题材热度混在一起，因此在测试时必须对 size 和行业做净化。

（三）估值变化 / 交易-基本面联动因子
1. pb_compress_20 = pb / lag20(pb) - 1
2. pe_re_rate_20 = pe_ttm / lag20(pe_ttm) - 1
3. value_recovery = rank_ind(bp) - rank_ind(turn_f)
逻辑是行业内“估值相对便宜但交易尚未拥挤”的股票更具后续重估空间。

（四）日频增强算子模板
对 daily_basic 的每一个候选底层变量 x，可以统一套以下算子：
- lag_k(x), k∈{1,5,20,60}
- roc_k(x)=x/lag_k(x)-1
- diff_k(x)=x-lag_k(x)
- ts_z_k(x)=(x-ma_k)/std_k
- ts_pct_k(x)=rolling_percentile
- cs_rank(x)：当日全市场横截面分位
- ind_rank_l{1,2,3}(x)：当日行业内分位
- bucket_5/10(x)：分桶
- neutralize(x, size + industry)
- interaction(x, y)：如 bp_rank * roe_rank

这样可以形成统一的通用函数库，而不是为每个因子写一次重复逻辑。

五、季度财务因子设计：精选高质量有效指标

季度因子不宜贪多，建议按七大类精选，并围绕“水平 + 变化 + 行业内位置 + 中性化”构建。

（一）盈利质量与盈利能力
1. roe / roe_dt / q_roe / q_dt_roe
2. roa / npta / roic
3. grossprofit_margin / netprofit_margin / q_netprofit_margin
4. profit_to_gr / q_profit_to_gr
设计要点：
- 用 roe_dt 替代单纯 roe，降低非经常损益噪声；
- 用 q_roe、q_profit_to_gr 抓边际变化；
- 与 bp、ep 联合，构建“便宜且高质量”。

（二）现金流质量
1. ocfps
2. ocf_to_or
3. ocf_to_profit
4. q_ocf_to_sales
5. ocf_yoy / cfps_yoy
核心思想是：利润最终必须兑现成现金流。A股中许多高增长公司在利润口径上很好看，但经营现金流质量弱。高 ocf_to_or、q_ocf_to_sales、ocf_to_profit 往往能有效剔除报表修饰风险。

（三）成长性与边际改善
1. tr_yoy / or_yoy
2. netprofit_yoy / dt_netprofit_yoy
3. q_sales_yoy / q_sales_qoq
4. q_op_qoq / q_netprofit_yoy
5. roe_yoy / bps_yoy
建议重点看“盈利增速是否优于收入增速”“扣非净利是否改善”“单季度环比是否加速”，避免只看年报口径导致滞后。

（四）营运效率
1. assets_turn
2. ar_turn
3. inv_turn
4. turn_days / invturn_days / arturn_days
制造、消费、医药里营运效率非常重要。建议采用行业内分位比较，因为不同行业周转特征差异极大。通常是“更高的周转率、更短的周转天数”更优，但一定用行业中性版本。

（五）杠杆与偿债
1. debt_to_assets
2. current_ratio / quick_ratio / cash_ratio
3. interestdebt / netdebt
4. ocf_to_shortdebt / ocf_to_debt
5. ebitda_to_debt / ebit_to_interest
这类指标更适合做风险控制、价值陷阱过滤和财务稳健筛选，不一定直接拿去做高换手 alpha，但作为组合约束非常有效。

（六）资本结构与资本效率
1. invest_capital
2. eqt_to_debt / debt_to_eqt
3. tangibleasset_to_debt
4. roic / roic_yearly
5. profit_to_op / op_to_debt
这里的关键是筛出“资本投入有效率”的公司，而不是资产堆积型公司。

（七）研发与可持续竞争力
1. rd_exp
2. rd_exp / total_revenue（若其他报表中可取到收入）
3. rd_exp 的同比/占比变化
Tushare 当前 fina_indicator 只有 rd_exp 原值，若配合利润表或营业收入即可构造研发强度；若本任务只用 fina_indicator，则 rd_exp 可做行业内规模调整后使用。

六、季度数据日频化：正确的时点处理

季度数据用在日度横截面时，必须严格遵循公告时点：
1. 每条财务记录以 ann_date 为开始生效日；
2. 对同一股票按 ann_date 排序，生效区间为 [ann_date, next_ann_date)；
3. 若同一季度多次更新，用最新 ann_date 的记录覆盖；
4. 日频回测时，以交易日去匹配最近一个已公告财务值；
5. 不能按 end_date 直接向前填充，否则一定前视。

建议在工程上先把季度表整理为“事件表”，再扩展成“日频 exposure 表”，并缓存为 parquet。

七、行业分位数、分桶与中性化：这是本任务的核心

（一）行业内分位数
对任一因子 x，在每个 trade_date 内按 l1/l2/l3 行业分组后计算百分位 rank。建议实现：
- ind_rank(x, level='l1')
- ind_rank(x, level='l2')
- ind_rank(x, level='l3', min_n=8, fallback='l2')
行业内分位可解决绝大多数行业结构偏差。例如银行低 PB、医药高 PB、钢铁低毛利、软件高毛利，这些都不能直接横比。

（二）行业分桶
为了让策略解释更直观，可在行业内把因子做 5 桶或 10 桶，再汇总成全市场组合。这样得到的是“先行业内选股，再行业间平均”的纯选股效果，而不是行业配置效果。建议同时输出：
- global_bucket：全市场直接分组
- ind_bucket：行业内分组后汇总
二者差异越大，说明该因子行业暴露越重。

（三）中性化
建议至少提供三种版本：
1. raw：原始因子
2. ind_neu：行业虚拟变量回归残差
3. ind_size_neu：行业 + ln(circ_mv) 回归残差
可选增加 liquidity 中性，即加 log(turnover_rate_f)。回归形式可用逐日横截面 OLS：
x_i = a + b*log(circ_mv_i) + Σ gamma_j * Industry_ij + e_i
取残差 e_i 作为中性化因子。对极端值先 winsorize，再回归，否则残差不稳。

（四）层级行业选择
- 价值/盈利类：优先 l1 或 l2，避免 l3 过细导致桶太少；
- 周转/利润率/成长类：优先 l2 或 l3，更贴近商业模式；
- 小样本行业：设置 min_n，小于阈值自动回退；
- 金融地产：可单独作为大类处理，因为财务口径差异显著。

八、推荐的复合因子

1. Value-Quality
0.35*rank_ind(ep_ttm) + 0.25*rank_ind(bp) + 0.20*rank_ind(roe_dt) + 0.20*rank_ind(ocf_to_or)
适合中低频，兼顾便宜与质量。

2. Margin-Improvement
0.25*rank_ind(q_profit_to_gr) + 0.25*rank_ind(q_ocf_to_sales) + 0.25*rank_ind(q_op_qoq) + 0.25*rank_ind(dt_netprofit_yoy)
适合景气改善与盈利拐点。

3. Anti-Crowded Value
0.4*rank_ind(bp) + 0.3*rank_ind(div_ttm) - 0.15*rank_ind(turnover_rate_f_z20) - 0.15*rank_ind(volume_ratio_z20)
适合防御与回撤控制。

4. Efficiency-Growth
0.3*rank_ind(assets_turn) + 0.2*rank_ind(ar_turn) + 0.2*rank_ind(inv_turn) + 0.3*rank_ind(q_sales_yoy)
适合制造消费内部比较。

5. Quality-Safety
0.25*rank_ind(current_ratio) + 0.25*rank_ind(ocf_to_debt) + 0.25*rank_ind(ebitda_to_debt) - 0.25*rank_ind(debt_to_assets)
偏风险控制型，可做过滤器。

九、测试体系：必须完整，不只看 IC

1. 未来收益定义
用 raw_daily 的复权前 close 至 close 计算 next_ret_1 / 5 / 10 / 20。若有复权价更好，否则至少保持定义一致。需过滤停牌、上市不满 60 日、价格异常、未来收益缺失样本。

2. 评价指标
- RankIC（日频横截面 spearman）
- IC 均值、ICIR、正 IC 占比
- 分组收益（5 组或 10 组）
- 多空收益（Q10-Q1）
- 年化收益、波动、夏普、最大回撤
- 换手率、覆盖率、样本数
- 按年份、按牛熊阶段、按市值分层、按行业分层表现
- 因子衰减：1/5/10/20 日 IC 曲线

3. 对照试验
每个候选因子至少做以下版本对照：
- 原始 raw
- winsor + zscore
- 行业内 rank
- 行业 + size 中性残差
- 与基本算子组合后的版本（lag/roc/ts_z）
只有经过这种“同因子不同处理方式”的测试，才能知道真正有效的是经济逻辑，还是处理方式。

4. 因子可实施性
A股中很多因子看起来 IC 很高，但换手极高、容量极差。测试中必须同步查看：
- top decile 平均 circ_mv
- top decile 平均 turnover_rate_f
- 分组持仓换手
- 涨跌停、ST、停牌过滤后的可交易收益

十、工程实现建议

目录建议如下：
- data_loader.py：读取 daily / daily_basic / industry / quarter
- tushare_downloader.py：从 TUSHARE_TOKEN 下载 fina_indicator
- preprocess.py：去重、时点处理、行业匹配、财务日频化
- transforms.py：winsorize、rank、zscore、neutralize、bucket、rolling operator
- factor_library_daily.py：日度因子定义
- factor_library_quarter.py：季度因子定义
- composer.py：复合因子
- backtest.py：IC、分组、多空、衰减、覆盖率
- run_factor_research.py：统一入口
为了复用性，底层通用函数一定要“输入列名，输出新列名”，避免写死某个因子。

十一、建议优先测试的一批因子

日度优先：
ep_ttm_rank_ind_l2、bp_rank_ind_l2、div_ttm_rank_ind_l1、turn_f_chg5_ind_rank、pb_compress_20_ind_rank、anti_crowding、value_recovery

季度优先：
roe_dt_ind_rank、ocf_to_or_ind_rank、q_ocf_to_sales_ind_rank、dt_netprofit_yoy_ind_rank、q_op_qoq_ind_rank、assets_turn_ind_rank、debt_to_assets_ind_rank_neg

复合优先：
Value-Quality、Margin-Improvement、Anti-Crowded Value

十二、落地建议与结论

本任务最重要的，不是机械地堆更多字段，而是建立一套稳健、可复用、时点正确、行业可比、可中性化、可测试的研究框架。日度 daily_basic 层适合做估值、交易拥挤度、注意力和估值变化；季度 fina_indicator 层适合做质量、成长、效率、现金流与杠杆；raw_daily 负责未来收益、交易过滤与行为补充。真正高质量的 alpha 往往来自三类结合：第一，行业内相对便宜；第二，质量或现金流不差；第三，边际变化在改善但交易不拥挤。建议你先用本文给出的 10~15 个核心因子跑第一轮，再根据 IC 稳定性、分组单调性、行业分布和容量，逐步筛成 4~6 个主因子做组合。

当前文档已配套 Python 工程脚本，可在你本机对 D:\Trading\data_ever_26_3_14\data\Raw_data\daily.parquet 与 daily_basic.parquet 直接运行；若环境变量 TUSHARE_TOKEN 已配置，脚本还会自动下载并缓存季度财务数据。这样既满足研究设计完整性，也满足工程可复现性。
