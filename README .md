

项目描述和改进

你现在的下载系统已经有了一个可用主干：`download_daily_2026.py` 和 `download_daily_basic_2026.py` 都是“按交易日拉取 → 分页 → 原子写 parquet → 写 `_state` 标记 → 并发执行”的模式；`ts_download_utils.py` 已经提供了 token 读取、重试、交易日历、分页抓取、原子落盘、状态清单、最大日期探测和进度条这些通用能力；`update_raw_data.py` 又把日频类数据、筹码、分钟数据和 compact 串起来了；`compact_raw_data.py` 还会先备份主文件再合并碎片。也就是说，你不是从零开始重构，而是从一个已经跑通的“原始下载框架”升级到“统一的数据工程框架”。

你的仓库当前范围也很明确：`src_data_download` 里已经有股票日线、每日指标、资金流、分钟线、股票基础信息、通用交易日下载器、验证和测试脚本；“数据文档”把数据域分成了股票、指数和股指期货/期权、宏观三块，但当前“宏观数据”目录里混入了“期权合约信息”和“期权日线行情”，说明数据域边界还没完全收紧。

结合你这次的新约束，我建议项目范围先冻结成下面四类：

- 股票：保留现有主线，不再扩域。
    
- A 股核心指数：只做 **不超过 8 只** 的主指数。
    
- 股指期货：只做 **CFFEX 股指期货**，不碰商品期货。
    
- 股指期权：只做 **CFFEX 股指期权**，不碰商品期权、ETF 期权的全市场大扩展。
    
- 宏观/外汇：先做少量高信息密度序列，不追求全量。Tushare 的 `index_basic`、`index_daily`、`index_dailybasic`、`fut_basic`、`fut_daily`、`fut_mapping`、`opt_basic`、`opt_daily`、`fx_obasic`、`fx_daily`、`cn_gdp`、`cn_cpi`、`cn_ppi` 等接口都支持这种“按接口单独建下载器”的做法，但它们的参数形态和限流规则差异很大，所以重构的关键不是多写几个脚本，而是把“任务切分方式”抽象出来。
    

---

# 一、现有代码的核心问题，不是“写法差”，而是“抽象还停在脚本层”

最明显的问题有三个。

第一，**下载脚本之间重复度很高**。  
`download_daily_2026.py` 和 `download_daily_basic_2026.py` 结构几乎相同：线程本地 `pro`、按交易日取 `trade_cal`、按 `limit=6000` 分页、写 `YYYYMMDD_o00000.parquet`、写每日 JSON 完成标记、线程池并发。它们本质上只差 `api = pro2.daily` 和 `api = pro2.daily_basic`，以及输出目录名。这个重复在股票域还可接受，但一旦你继续加指数、股指期货、股指期权和宏观接口，复制脚本会迅速失控。

第二，**你现在已经有通用能力，但没有把它们正式上升为“下载框架约定”**。  
`ts_download_utils.py` 里已经有 `retry_call`、`iter_trade_dates_yyyymmdd`、`paginated_fetch`、`write_parquet_atomic`、`StateManifest`、`get_parquet_max_date`、`Progress`。这说明你已经写出了 70% 的框架基础设施，但上层下载脚本还没有统一走同一个 Runner/Spec 体系。

第三，**“数据域”和“任务切分维度”还没分开**。  
股票日频类接口适合“按交易日切任务”；指数日线更适合“按指数代码切长时间窗口”；期货合约表是快照/字典类；期货连续映射是桥表；期权合约信息是合约维表；宏观数据是月度/季度 period 序列。现在如果继续把所有新增接口都塞进 `download_xxx_2026.py` 这种按交易日扫描的模版里，后面维护会非常差。Tushare 官方文档本身已经透露出这些接口的任务粒度差异：`daily_basic` 单次 6000 条、按日线循环提取全历史；`index_daily` 单次 8000 条，适合指定代码和时间段；`index_dailybasic` 目前只覆盖 6 个大盘指数且单次 3000 条；`fut_daily` 单次 2000 条；`fut_mapping` 单次 2000 条；`opt_daily` 单次 15000 条；`cn_gdp` 和 `cn_cpi/cn_ppi` 则是按季度/月度 period 查询。

---

# 二、这次重构的总目标

这次不要把目标定成“把所有下载脚本都改漂亮”，而要定成：

**先把数据稳定下载好，同时把参数差异、溯源、断点续跑、测试、后处理全部纳入统一框架。**

我建议你把重构目标定成四条：

1. **统一下载执行模型**：不同接口共用一个 Runner，但可以选择不同 TaskBuilder。
    
2. **统一原始落库约定**：所有数据都先落 raw/bronze 层，保留原字段和抓取溯源。
    
3. **统一验证约定**：不是每个脚本自己 print，而是统一输出 verify report。
    
4. **统一测试体系**：单元测试、契约测试、集成测试、回归测试分层。
    

---

# 三、建议的目标工程结构

建议把 `src_data_download` 重构成下面这样：

`src_data_download/   core/     dataset_spec.py     runner.py     task_builders.py     sinks.py     state_store.py     lineage.py     exceptions.py   adapters/     tushare_client.py     stock.py     index.py     futures.py     options.py     macro.py     fx.py   datasets/     stock_daily.py     stock_daily_basic.py     stock_moneyflow.py     stock_suspend.py     stock_limit.py     stock_basic.py     stock_minutes.py      index_basic.py     index_daily.py     index_dailybasic.py      cffex_fut_basic.py     cffex_fut_daily.py     cffex_fut_mapping.py      cffex_opt_basic.py     cffex_opt_daily.py      macro_gdp.py     macro_cpi.py     macro_ppi.py     macro_money_supply.py     macro_social_financing.py     macro_pmi.py      fx_basic.py     fx_daily.py   jobs/     bootstrap_history.py     update_incremental.py     compact_job.py     verify_job.py     catalog_dump.py   tests/     unit/     integration/     contract/     regression/`

这不是为了“目录好看”，而是为了把四类变化拆开：

- `core/`：下载框架本身
    
- `adapters/`：Tushare 接口调用差异
    
- `datasets/`：每个数据集的声明式配置
    
- `jobs/`：历史初始化、每日更新、合并、验证这些操作流
    

这样你以后再加接口，不再需要复制一整个 `download_xxx_2026.py`。

---

# 四、核心抽象：不要再以“脚本”为中心，而要以 `DatasetSpec` 为中心

这是重构里最关键的一步。

建议你的每个数据集都变成一个声明对象，大概像这样：

`from dataclasses import dataclass, field from typing import Literal  @dataclass(frozen=True) class DatasetSpec:     name: str     api_name: str     asset_class: Literal["stock", "index", "futures", "options", "macro", "fx"]     fetch_mode: Literal["trade_date", "ts_code_range", "snapshot", "period_month", "period_quarter"]     pk_cols: tuple[str, ...]     partition_cols: tuple[str, ...]     date_col: str | None     required_fields: tuple[str, ...] = ()     optional_fields: tuple[str, ...] = ()     limit: int = 2000     supports_offset: bool = True     supports_trade_cal: bool = False     exchange_filter: str | None = None     market_filter: str | None = None`

然后不同数据集只写配置，不重复写下载骨架。

例如：

- `stock_daily`: `fetch_mode="trade_date"`, `api_name="daily"`, `limit=6000`, `date_col="trade_date"`
    
- `index_daily`: `fetch_mode="ts_code_range"`, `api_name="index_daily"`, `limit=8000`, `date_col="trade_date"`
    
- `cffex_fut_mapping`: `fetch_mode="ts_code_range"`, `api_name="fut_mapping"`, `limit=2000`
    
- `macro_gdp`: `fetch_mode="period_quarter"`, `api_name="cn_gdp"`, `date_col="quarter"`
    
- `fx_basic`: `fetch_mode="snapshot"`, `api_name="fx_obasic"`
    

这样你真正复用的是框架，数据集只声明差异。

---

# 五、TaskBuilder 才是处理“参数具体上有许多不同”的关键

你特别强调“每个下载的参数具体上有许多不同，要全面处理和保留溯源”，我完全同意。  
所以真正该抽象的不是 `api_name`，而是 **任务生成器**。

## 1. `TradeDateTaskBuilder`

给股票日频类接口用。

适用：

- `daily`
    
- `daily_basic`
    
- `moneyflow`
    
- `stk_limit`
    
- `suspend_d`
    

逻辑：

- 用 `trade_cal` 取开市日
    
- 每个 `trade_date` 是一个任务
    
- 每个任务分页抓取直到 `got < limit`
    
- 成功后写 `state[trade_date]=done`
    

你现有股票脚本就是这个模式。

## 2. `CodeRangeTaskBuilder`

给指数、股指期货、股指期权日线用。

适用：

- `index_daily`
    
- `index_dailybasic`
    
- `fut_daily`
    
- `fut_mapping`
    
- `opt_daily`
    

逻辑：

- 先拿 universe（指数代码、合约代码）
    
- 每个 `ts_code + date window` 是一个任务
    
- 如果该接口单次上限足够大，就按年/半年切窗口
    
- 每个任务分页抓取直到 `got < limit`
    

这比“按全市场交易日扫”更适合指数和衍生品。

## 3. `SnapshotTaskBuilder`

给字典表和基础信息表。

适用：

- `index_basic`
    
- `fut_basic`
    
- `opt_basic`
    
- `fx_obasic`
    
- `stock_basic`
    

逻辑：

- 不按交易日
    
- 一次全量抓取或按交易所分片抓取
    
- 落快照文件，保留 `fetched_at` 和 `source_params`
    

## 4. `PeriodTaskBuilder`

给宏观月/季频序列。

适用：

- `cn_gdp`
    
- `cn_cpi`
    
- `cn_ppi`
    
- `cn_m`
    
- `cn_sf`
    
- `cn_pmi`
    

逻辑：

- 月度用 `start_m/end_m`
    
- 季度用 `start_q/end_q`
    
- 周期序列一次全量可拉完时，不要假装走交易日框架
    

这一步做对了，后面的脚本会非常干净。

---

# 六、按你的新范围，推荐的数据集清单

## A. 股票：保持现有 6 个日频核心 + 2 个基础/分钟扩展

保留并标准化：

- `daily`
    
- `daily_basic`
    
- `moneyflow`
    
- `stk_limit`
    
- `suspend_d`
    
- `cyq_perf`
    
- `stock_basic`
    
- `stk_mins_60min`
    

这是你现在已成型的主线。`update_raw_data.py` 也已经把 `daily,daily_basic,moneyflow,stk_limit,suspend_d,cyq_perf,stk_mins_60min` 作为默认更新集。

## B. A 股指数：建议 7 只主指数，最多 8 只

先说我建议的主清单：

1. `000001.SH` 上证综指
    
2. `399001.SZ` 深证成指
    
3. `000300.SH` 沪深300
    
4. `000016.SH` 上证50
    
5. `000905.SH` 中证500
    
6. `000852.SH` 中证1000
    
7. `399006.SZ` 创业板指
    

可选第 8 只：  
8. `000688.SH` 科创50

原因不是“它们最有名”，而是这 7-8 只已经把你后面量化研究里最常见的市场 beta、大小盘风格、蓝筹/成长风格和科创/创业板风格都覆盖了。

这里有一个重要现实约束：

- `index_basic` 是全量指数元数据接口，市场和类别非常多。
    
- 但 `index_dailybasic` 官方文档明确说 **目前只提供上证综指、深证成指、上证50、中证500、中小板指、创业板指** 六个指数的每日指标。也就是说，`000300.SH`、`000852.SH`、`000688.SH` 这类指数你可以稳定拿到 `index_daily`，但未必能从 `index_dailybasic` 拿到同等覆盖的每日估值/换手等指标。
    

所以工程上要分两层：

- **Tier 1: 行情主指数池**：上面 7-8 只，全都下载 `index_daily`
    
- **Tier 2: 指标覆盖池**：只对 `index_dailybasic` 实际支持的那几只下载每日指标
    

不要强行要求两层完全同构。

## C. 股指期货：只做 CFFEX 的 4 条主线

推荐：

- `IF` 沪深300股指期货
    
- `IH` 上证50股指期货
    
- `IC` 中证500股指期货
    
- `IM` 中证1000股指期货
    

中金所官网当前产品页明确有沪深300、上证50、中证500、中证1000股指期货产品。

工程上分三张表：

- `cffex_fut_basic`
    
- `cffex_fut_daily`
    
- `cffex_fut_mapping`
    

`fut_basic` 给合约列表；`fut_daily` 给月合约日线；`fut_mapping` 给连续/主力到月合约的映射。Tushare 文档对这三者的角色和参数差异写得很清楚：`fut_basic` 是合约列表、`fut_daily` 是日线、`fut_mapping` 是连续合约与月合约映射。

**关键建议**：  
不要在 raw 层直接把“主力连续价格”当原始事实表。  
raw 层只存：

- 月合约日线
    
- 连续映射关系
    

真正的连续合约价格曲线，在 silver/gold 层自己派生。


---

## D. 股指期权：只做 CFFEX 的 3 条主线

推荐：

- `IO` 沪深300股指期权
    
- `HO` 上证50股指期权
    
- `MO` 中证1000股指期权
    

中金所官网当前产品页明确包含沪深300股指期权、中证1000股指期权、上证50股指期权这三类权益类期权产品。([中国金融期货交易所](https://www.cffex.com.cn/cn/index.html?utm_source=chatgpt.com "中国金融期货交易所"))

工程上分两张表：

- `cffex_opt_basic`
    
- `cffex_opt_daily`
    

`opt_basic` 给合约维表；`opt_daily` 给交易事实表。Tushare 文档显示，`opt_basic` 提供 `ts_code`、`exchange`、`name`、`opt_code`、`call_put`、`exercise_type`、`exercise_price`、`maturity_date`、`list_date`、`delist_date` 等字段；`opt_daily` 提供 `trade_date`、`pre_settle`、`open/high/low/close`、`settle`、`vol`、`amount`、`oi` 等字段，而且单次最大 15000 条，支持按代码或按日期提取。([Tushare](https://tushare.pro/document/2?doc_id=158&utm_source=chatgpt.com "Tushare数据"))

### 1. 股指期权的核心设计原则

**第一，先 basic，后 daily。**  
期权 universe 不是“指数代码集合”，而是“合约集合”。如果你没有先把 `opt_basic` 拉下来，你根本不知道某一天活跃的合约有哪些、它们的行权价是多少、到期日是什么、看涨看跌如何区分。

**第二，option 的 raw 层必须是 contract-first，而不是 date-first。**  
股票日线可以“按交易日扫全市场”，因为 universe 相对稳定；股指期权不行。期权合约按到期月、行权价、看涨看跌迅速扩张，而且有上市/摘牌生命周期。  
所以下载策略应该是：

1. 先抓 `opt_basic(exchange='CFFEX')`
    
2. 依据 `list_date <= d <= delist_date` 生成某日活跃合约池
    
3. 对活跃池抓 `opt_daily`
    
4. 把合约维表和日线事实表解耦保存
    

**第三，原始层不做隐波、不做曲面。**  
原始层只保留 Tushare 给的原始字段和抓取溯源；隐含波动率、期限结构、偏度、跨式价格等都应该留到 silver/gold 层。

### 2. 建议的数据模型

#### `dim_option_contract`

主键：

- `ts_code`
    

核心字段：

- `ts_code`
    
- `exchange`
    
- `name`
    
- `opt_code`
    
- `opt_type`
    
- `call_put`
    
- `exercise_type`
    
- `exercise_price`
    
- `s_month`
    
- `maturity_date`
    
- `list_price`
    
- `list_date`
    
- `delist_date`
    
- `last_edate`
    
- `last_ddate`
    
- `quote_unit`
    
- `min_price_chg`
    
- `fetched_at`
    
- `source_api`
    
- `source_params`
    
- `snapshot_id`
    

用途：

- 生成活跃合约池
    
- 给期权链做维度补充
    
- 给后续隐波和到期结构派生提供 contract metadata
    

#### `fact_option_daily`

主键：

- `ts_code`
    
- `trade_date`
    

核心字段：

- `ts_code`
    
- `trade_date`
    
- `exchange`
    
- `pre_settle`
    
- `pre_close`
    
- `open`
    
- `high`
    
- `low`
    
- `close`
    
- `settle`
    
- `vol`
    
- `amount`
    
- `oi`
    
- `fetched_at`
    
- `source_api`
    
- `source_params`
    

用途：

- 构成期权日线事实表
    
- 与 `dim_option_contract` join 后形成每日期权链
    

### 3. 建议的下载任务设计

#### `cffex_opt_basic`

- `fetch_mode = "snapshot"`
    
- `api_name = "opt_basic"`
    
- 参数：
    
    - `exchange="CFFEX"`
        
- 输出：
    
    - `raw/options/cffex_opt_basic/snapshot_date=YYYYMMDD/part-000.parquet`
        

这张表建议每次都保留“全量快照”，不要直接覆盖旧文件。因为合约信息会变，快照本身就是溯源的一部分。

#### `cffex_opt_daily`

- `fetch_mode = "ts_code_range"`
    
- `api_name = "opt_daily"`
    

任务生成方式建议为：

- 先从最新 `cffex_opt_basic` 快照里筛出合约
    
- 对每个 `ts_code` 按月或季度切时间窗
    
- 每个任务：
    
    - `ts_code`
        
    - `start_date`
        
    - `end_date`
        
- 如果行数超限，再分页 offset
    

为什么不用 `trade_date` 粒度扫全市场？  
因为 `opt_daily` 支持按代码和时间提取，而且股指期权合约集合相对可控；你只做 CFFEX 三大股指期权，按合约切更符合期权生命周期逻辑，也更利于断点续跑。`opt_daily` 官方文档也明确支持 `ts_code`、`trade_date`、`start_date`、`end_date` 和 `exchange` 参数。([Tushare](https://tushare.pro/document/2?doc_id=159&utm_source=chatgpt.com "Tushare数据"))

### 4. 股指期权的验证规则

#### 结构验证

- `opt_basic` 必须包含：
    
    - `ts_code`
        
    - `call_put`
        
    - `exercise_price`
        
    - `maturity_date`
        
    - `list_date`
        
    - `delist_date`
        
- `opt_daily` 必须包含：
    
    - `ts_code`
        
    - `trade_date`
        
    - `close`
        
    - `settle`
        
    - `oi`
        

#### 生命周期验证

- 任意 `fact_option_daily.trade_date` 必须满足：
    
    - `list_date <= trade_date <= delist_date`
        
- 如果出现越界记录，标为数据异常，进入 verify report
    

#### 横截面验证

对每个交易日，按底层合约、到期月和 `call_put` 分组，检查：

- 是否存在明显不合理的 strike 缺口
    
- 是否出现 `oi<0`、`vol<0`
    
- 是否同一 `ts_code + trade_date` 重复
    

### 5. 股指期权后续派生，但不进入第一期下载范围

后续可扩展但第一期不做：

- 每日 option chain 宽表
    
- ATM/OTM 标识
    
- 隐含波动率
    
- 到期结构曲线
    
- skew / term structure 因子
    

---

## E. 宏观数据：只做少量高价值序列，统一成长表

你当前“宏观数据”目录里列了 GDP、CPI、PPI、社融、货币供应量、PMI、外汇、黄金等，但目录边界还不够干净。后续应把真正的宏观序列和市场交易型数据拆开。

第一期建议只做以下宏观序列：

- `cn_gdp`
    
- `cn_cpi`
    
- `cn_ppi`
    
- `cn_m`
    
- `cn_sf`
    
- `cn_pmi`
    

其中：

- `cn_gdp` 是季度序列，单次可取全量，参数是 `q/start_q/end_q`。([Tushare](https://tushare.pro/document/2?doc_id=227&utm_source=chatgpt.com "GDP数据 - Tushare"))
    
- `cn_cpi` 是月度序列，参数是 `m/start_m/end_m`。([Tushare](https://tushare.pro/document/2?doc_id=228&utm_source=chatgpt.com "Tushare数据"))
    
- `cn_ppi` 与 `cn_cpi` 同属月度宏观序列，参数形态相近。([Tushare](https://tushare.pro/document/2?doc_id=228&utm_source=chatgpt.com "Tushare数据"))
    

### 1. 宏观设计原则

**第一，宏观不是交易日面板，而是 period 序列。**  
不要把 GDP/CPI/PPI 当成股票日线那样“按交易日抓”。它们天然是月频/季频，任务应按 `period` 构造。

**第二，宏观要从一开始就引入 as-of 语义。**  
单纯存 period 值不够。研究和回测中，真正重要的是某个交易日市场当时能看到什么，所以要保留：

- `period`
    
- `release_date`
    
- `asof_date`
    
- `fetched_at`
    

即便 Tushare 接口本身没有总是直接给完整发布时间字段，你也要在工程层预留这些字段，后续可补充发布日历。

**第三，宏观建议统一成长表。**  
不要 GDP 一张宽表、CPI 一张宽表、PPI 一张宽表直接散落在 feature 层。raw 层可以按接口分别落，但 silver 层建议统一成长表模型。

### 2. 建议的数据模型

#### raw 层

每个接口单独保存：

- `raw/macro/cn_gdp/...`
    
- `raw/macro/cn_cpi/...`
    
- `raw/macro/cn_ppi/...`
    
- `raw/macro/cn_m/...`
    
- `raw/macro/cn_sf/...`
    
- `raw/macro/cn_pmi/...`
    

#### silver 层统一表：`fact_macro_series`

建议字段：

- `series_id`
    
- `series_name`
    
- `source_api`
    
- `frequency` (`M` / `Q`)
    
- `period`
    
- `value_type`
    
- `value`
    
- `unit`
    
- `release_date`
    
- `asof_date`
    
- `fetched_at`
    
- `source_params`
    

示例：

|series_id|frequency|period|value_type|value|
|---|---|---|---|---|
|CN_GDP|Q|2024Q1|gdp|...|
|CN_GDP|Q|2024Q1|gdp_yoy|...|
|CN_CPI|M|202403|nt_yoy|...|
|CN_CPI|M|202403|nt_mom|...|

这样你后面做宏观特征、滞后项、as-of 对齐会简单很多。

### 3. 宏观下载任务设计

#### `macro_gdp`

- `fetch_mode = "period_quarter"`
    
- `api_name = "cn_gdp"`
    
- 参数：
    
    - `start_q`
        
    - `end_q`
        
- 单次可全量，初始化时直接全历史
    
- 增量更新时每次拉最近 8 个季度即可，防止修订遗漏
    

#### `macro_cpi / macro_ppi / macro_money_supply / macro_social_financing / macro_pmi`

- `fetch_mode = "period_month"`
    
- 参数：
    
    - `start_m`
        
    - `end_m`
        
- 初始化：全量
    
- 增量：滚动回拉最近 24 个月
    

为什么建议回拉？  
因为宏观数据存在修订和补充字段，滚动覆盖最近若干期比“只拉最新一个月”更稳。

### 4. 宏观验证规则

- `period` 必须唯一到 `series_id + value_type`
    
- 月频格式必须是 `YYYYMM`
    
- 季频格式必须是 `YYYYQn`
    
- 不允许未来 period 出现在历史抓取中
    
- 同一 series 最近 N 期如果出现大面积空值，要告警
    
- 宏观表必须有 `fetched_at`，没有则视为 lineage 缺失
    

---

## F. 外汇与黄金：只保留少量典型资产，显式写明选择依据

Tushare 的 `fx_obasic` 当前只覆盖 FXCM 交易商数据，分类很多，不只有货币对，还有指数、大宗商品、金属、加密货币和外汇篮子。`fx_daily` 是 GMT 日期，不是北京时间。([Tushare](https://tushare.pro/document/2?doc_id=178&utm_source=chatgpt.com "Tushare数据"))

因此第一期不要“把外汇全下了”，而是选少量高信息密度标的。

### 1. 推荐第一期标的

#### 外汇货币对（FX）

- `USDCNH`
    
- `USDJPY`
    
- `EURUSD`
    
- `GBPUSD`
    

#### 金属（METAL）

- `XAUUSD`
    

#### 外汇篮子（FX_BASKET）

- `USDOLLAR`
    

### 2. 选择理由

- `USDCNH`：人民币相关风险和中国资产最直接
    
- `USDJPY`：全球风险偏好、套息交易敏感
    
- `EURUSD`：全球最核心货币对
    
- `GBPUSD`：补充欧美汇率结构
    
- `XAUUSD`：避险与美元镜像资产
    
- `USDOLLAR`：美元整体强弱代理
    

### 3. 数据模型

#### `dim_fx_symbol`

来自 `fx_obasic`：

- `ts_code`
    
- `name`
    
- `classify`
    
- `exchange`
    
- `min_unit`
    
- `max_unit`
    
- `pip`
    
- `pip_cost`
    
- `trading_hours`
    
- `break_time`
    
- `fetched_at`
    

#### `fact_fx_daily`

来自 `fx_daily`：

- `ts_code`
    
- `trade_date` （GMT）
    
- `bid_open`
    
- `bid_close`
    
- `bid_high`
    
- `bid_low`
    
- `ask_open`
    
- `ask_close`
    
- `ask_high`
    
- `ask_low`
    
- `tick_qty`
    
- `exchange`
    
- `fetched_at`
    

### 4. 下载任务设计

#### `fx_basic`

- `fetch_mode = "snapshot"`
    
- `api_name = "fx_obasic"`
    
- 初始化一次全量拉取
    
- silver 层再按 `classify in ('FX','METAL','FX_BASKET')` 和代码白名单筛
    

#### `fx_daily`

- `fetch_mode = "ts_code_range"`
    
- `api_name = "fx_daily"`
    
- 每个 `ts_code` 按年或半年切窗口
    

注意：  
`fx_daily.trade_date` 是 GMT 日期，比北京时间晚一天。多资产对齐时必须显式处理时区，不然会和 A 股交易日错位。([Tushare](https://tushare.pro/document/2?doc_id=179&utm_source=chatgpt.com "Tushare数据"))

### 5. 验证规则

- `ts_code + trade_date` 唯一
    
- `ask_*` 不应系统性小于 `bid_*`
    
- `tick_qty` 不应为负
    
- 与 A 股/指数做对齐时必须通过时区适配器，不允许直接裸 join
    

---

## G. catalog 与 universe 管理：先“看 basic”，再固定白名单

你特别强调“指数有几千只，要先 basic 看一下有什么，再推荐和选择”，这个要求非常对。  
所以工程上要新增一个通用 catalog 作业，而不是把 universe 写死在脚本里。

### 1. 建议新增的 catalog 作业

- `jobs/catalog_dump.py`
    

输出：

- `catalog/index_basic_full.parquet`
    
- `catalog/fut_basic_cffex.parquet`
    
- `catalog/opt_basic_cffex.parquet`
    
- `catalog/fx_obasic_full.parquet`
    

### 2. 建议的白名单配置文件

```yaml
core_indices:
  - 000001.SH
  - 399001.SZ
  - 000300.SH
  - 000016.SH
  - 000905.SH
  - 000852.SH
  - 399006.SZ
  - 000688.SH

core_index_dailybasic_supported:
  - 000001.SH
  - 399001.SZ
  - 000016.SH
  - 000905.SH
  - 399006.SZ

core_cffex_futures_prefix:
  - IF
  - IH
  - IC
  - IM

core_cffex_options_prefix:
  - IO
  - HO
  - MO

core_fx_symbols:
  - USDCNH
  - USDJPY
  - EURUSD
  - GBPUSD
  - XAUUSD
  - USDOLLAR
```

后续 universe 改动只动配置，不动下载逻辑。

---

## H. 溯源与审计：必须成为框架默认能力

你前面强调“不同参数和多样情况的全面处理和溯源功能的保留”，这部分必须做成默认行为，而不是可选功能。

### 1. 每个原始文件的 sidecar metadata

每个 parquet 文件旁边生成一个 `.meta.json`：

```json
{
  "dataset": "cffex_opt_daily",
  "api_name": "opt_daily",
  "task_key": "sha1(...)",
  "request_params": {
    "ts_code": "IO2406-C-3500.CFFEX",
    "start_date": "20240401",
    "end_date": "20240430",
    "offset": 0,
    "limit": 15000
  },
  "fetched_at": "2026-04-14T23:00:00+08:00",
  "rows": 18,
  "columns": ["ts_code", "trade_date", "open", "high", "..."],
  "code_version": "git_sha",
  "checksum": "sha256:..."
}
```

### 2. state 存储统一成 manifest

不要让新数据集继续无限生成 `_state/*.json` 小文件。  
统一用：

- `state/stock_daily.state.json`
    
- `state/index_daily.state.json`
    
- `state/cffex_fut_daily.state.json`
    
- `state/cffex_opt_daily.state.json`
    
- `state/macro_gdp.state.json`
    

记录：

- `task_key`
    
- `dataset`
    
- `params_hash`
    
- `status`
    
- `rows`
    
- `updated_at`
    
- `latest_file`
    

### 3. 统一任务键

建议：

```text
task_key = sha1(dataset_name + canonical_json(request_params))
```

这样：

- 可幂等
    
- 可追溯
    
- 可重放
    
- verify 时能对账
    

---

## I. 测试体系：把“测试”升级成项目核心，而不是附属脚本

这一部分是后半文档里最重要的，因为你明确要求“注重测试”。

### 1. 单元测试（不打真实网络）

覆盖对象：

#### `core/`

- `DatasetSpec`：合法性校验
    
- `TaskBuilder`：任务生成数量、边界日期、空 universe
    
- `Runner`：分页终止、重试逻辑、异常透传
    
- `StateStore`：幂等、重复更新、失败恢复
    
- `LineageWriter`：sidecar 内容完整性
    

#### `ts_download_utils` 拆分后的工具函数

- `retry_call`
    
- `write_parquet_atomic`
    
- `get_parquet_max_date`
    
- 时间转换函数
    
- 目录创建与临时文件清理
    

### 2. 契约测试（接口参数级）

每个 Tushare dataset 都要有参数契约测试：

#### 示例

- `stock_daily`：
    
    - 必须允许 `trade_date`
        
    - 支持 `start_date/end_date`
        
- `index_dailybasic`：
    
    - 不应假设支持任意指数
        
- `opt_basic`：
    
    - 必须支持 `exchange`
        
    - 输出必须含 `call_put/exercise_price/list_date/delist_date`
        
- `fx_daily`：
    
    - 必须显式标记 GMT
        
- `cn_gdp`：
    
    - 必须用 `start_q/end_q`
        
- `cn_cpi`：
    
    - 必须用 `start_m/end_m`
        

### 3. 集成测试（mock client）

构造 fake Tushare client：

- 返回多页 DataFrame
    
- 模拟空页
    
- 模拟 intermittent failure
    
- 模拟 schema 不一致
    

验证：

- raw 文件是否正确生成
    
- metadata 是否写出
    
- state 是否更新
    
- compact 后是否主键唯一
    
- verify 是否能正确报缺失任务
    

### 4. smoke test（真实小样本）

每个新数据集都要有一条真接口 smoke case：

- `index_daily`: `000300.SH` 最近 5 个交易日
    
- `index_dailybasic`: `000001.SH` 最近 5 个交易日
    
- `cffex_fut_daily`: 选一个活跃 IF 合约最近 5 天
    
- `cffex_opt_basic`: `exchange='CFFEX'`
    
- `cffex_opt_daily`: 选一个活跃 IO 合约最近 5 天
    
- `macro_gdp`: 最近 4 个季度
    
- `fx_daily`: `USDCNH` 最近 10 天
    

### 5. 回归测试

保留一组小型黄金样本 parquet：

- 股票日线
    
- 指数日线
    
- 股指期货日线
    
- 股指期权日线
    
- GDP/CPI
    
- FX 日线
    

每次重构都比对：

- 行数
    
- 主键唯一数
    
- 最大日期
    
- 核心字段集
    
- hash/checksum
    

---

## J. verify 与 compact：继续保留，但要升级成统一 job

你现有思路是对的：先 raw 下载，再 compact，再 verify。  
后续要把它们变成 dataset-aware 的统一作业。

### 1. `compact_job`

职责：

- 收集 raw parts
    
- 读取对应 DatasetSpec
    
- 对齐 schema
    
- 去重
    
- 写 silver 主文件
    
- 生成 compact report
    

### 2. `verify_job`

职责：

- 检查 state 和文件一致性
    
- 检查主键重复
    
- 检查时间范围缺口
    
- 检查必要字段存在
    
- 检查 lineage sidecar 完整性
    
- 输出 `verify_report.json` 与 `verify_report.md`
    

### 3. 对四类数据的 verify 模板

#### 股票

- 按交易日检查缺口
    
- `ts_code + trade_date` 唯一
    

#### 指数

- 按 `ts_code + trade_date` 检查缺口
    
- `index_dailybasic` 只对支持池检查
    

#### 股指期货

- 月合约日线主键唯一
    
- continuous mapping 不允许同一日同一连续代码映射多个月合约
    

#### 股指期权

- 生命周期一致性
    
- `ts_code + trade_date` 唯一
    
- `list_date <= trade_date <= delist_date`
    

#### 宏观

- `series_id + period + value_type` 唯一
    
- period 格式合法
    

#### FX

- `ts_code + trade_date` 唯一
    
- GMT 日期标记存在
    

---

## K. 实施顺序：后半段范围的落地节奏

### Phase 3.1：先接 CFFEX 股指期权

原因：

- universe 可控
    
- 只做 3 条主线
    
- `opt_basic + opt_daily` 模型清晰
    
- 能很好验证 contract-first 框架
    

交付：

- `cffex_opt_basic`
    
- `cffex_opt_daily`
    
- 活跃合约池构建器
    
- option verify 模板
    

### Phase 3.2：再接宏观

原因：

- 下载量小
    
- 更容易验证
    
- 但 period 逻辑与交易日不同，能检验框架泛化能力
    

交付：

- `macro_gdp`
    
- `macro_cpi`
    
- `macro_ppi`
    
- `macro_money_supply`
    
- `macro_social_financing`
    
- `macro_pmi`
    
- `fact_macro_series` silver 模型
    

### Phase 3.3：最后接 FX

原因：

- 有 GMT 时区差异
    
- 有分类筛选逻辑
    
- 更适合作为跨市场扩展的最后一步
    

交付：

- `fx_basic`
    
- `fx_daily`
    
- `dim_fx_symbol`
    
- `fact_fx_daily`
    
- 时区转换适配器
    

---

## L. 交付物清单：你最终应该产出的不是“几段脚本”，而是一套工程资产

### 代码层

- `core/`
    
- `adapters/`
    
- `datasets/`
    
- `jobs/`
    

### 配置层

- `config/universe.yaml`
    
- `config/runtime.yaml`
    
- `config/storage.yaml`
    

### 数据层

- `raw/`
    
- `silver/`
    
- `catalog/`
    
- `state/`
    
- `lineage/`
    

### 文档层

- `docs/refactor_plan.md`
    
- `docs/dataset_catalog.md`
    
- `docs/testing_strategy.md`
    
- `docs/verify_rules.md`
    

### 测试层

- `tests/unit/`
    
- `tests/contract/`
    
- `tests/integration/`
    
- `tests/regression/`
    

---

## M. 后半部分的最终结论

从 CFFEX 股指期权往后，你真正需要建立的是一套**“按数据本质选任务粒度”的统一下载框架**：

- 股票：按交易日
    
- 指数：按代码区间
    
- 股指期货：按合约区间 + 连续映射
    
- 股指期权：先合约维表，再日线事实表
    
- 宏观：按月/季 period
    
- 外汇：按代码区间，并显式处理 GMT
    

这套框架一旦搭好，你后面再扩展数据集时，就不再是“复制一个新的 `download_xxx_2026.py`”，而是“新增一个 DatasetSpec + 一个 adapter 配置 + 一组契约测试”。

如果你要，我下一条可以继续把这份后半文档再推进一步，直接给你两样更落地的东西中的一个：  
要么我把这整份文档整理成**完整的 markdown 成稿结构**；要么我直接从这里往下写 **`DatasetSpec + Runner + CFFEX option/macro/fx` 的代码骨架设计文档**。
