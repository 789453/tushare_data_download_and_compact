下面给你一份可直接指导编程改造的工程文档。它不是“说明书风格”的泛讲，而是面向落地实施的设计稿：明确最终项目形态、代码结构、模块职责、接口、状态管理、增量更新、测试、日志与进度展示，以及当前仓库每个关键文件应该怎么迁移。本文档基于我重新核对的仓库现状：仓库根目录已经有 `src_data_download`、`src_new_data_download`、`tests`、`pytest.ini`，而 `src_data_download` 下目前仍主要是脚本式文件，如 `download_daily_2026.py`、`download_daily_basic_2026.py`、`download_trade_date_generic.py`、`ts_download_utils.py`、`update_raw_data.py`、`compact_raw_data.py` 等；README 则已经提出了向 `core/ + adapters/ + datasets/ + jobs/` 迁移的方向。与此同时，`tests/unit`、`tests/integration`、`tests/contract` 已经在引用 `src_data_download.core.dataset_spec`、`Runner`、`Task`、`src_data_download.datasets` 等模块，但这些路径并未出现在当前 `src_data_download` 可见目录中，说明仓库正处于“README 和测试先行，主实现仍停留在旧脚本层”的过渡态。([GitHub](https://github.com/789453/tushare_data_download_and_compact "https://github.com/789453/tushare_data_download_and_compact"))

***

# 一、改造目标

本次改造的最终目标，不是“再多加几份下载脚本”，而是把项目升级为一个三层协同的数据工程系统：

1. **Parquet** 继续作为原始落地和对外交换格式，负责保存原始抓取结果、快照、分片和审计副本。DuckDB 能直接高效读取和写出 Parquet，并支持在扫描 Parquet 时做过滤下推和列裁剪，因此 Parquet 仍然应该保留为底层文件格式。([DuckDB](https://duckdb.org/docs/current/data/parquet/overview.html?utm_source=chatgpt.com "Reading and Writing Parquet Files"))
2. **DuckDB** 作为本地分析型主引擎，负责 raw → silver 的合并、去重、统一 schema、增量 upsert、验证查询、统计报表、导出标准 Parquet。DuckDB 是嵌入式分析数据库，支持持久化 `.duckdb` 文件，也支持 `MERGE INTO` 做 upsert，特别适合你这个“本地批量数据工程 + 高并发下载后合并”的场景。([DuckDB](https://duckdb.org/docs/current/clients/python/overview.html?utm_source=chatgpt.com "Python API"))
3. **SQLite3** 作为控制平面数据库，负责任务状态、水位、文件清单、失败重试、作业运行记录、校验报告索引等“小而关键”的元数据。Python 标准库自带 `sqlite3`，SQLite 支持 `ON CONFLICT` UPSERT，且 WAL 模式可提升并发读写场景下的实用性，因此很适合做 job metadata store，而不适合承担大事实表。([Python documentation](https://docs.python.org/3/library/sqlite3.html "https://docs.python.org/3/library/sqlite3.html"))

结论就是：**Parquet 做 raw/snapshot/file exchange，DuckDB 做事实表与标准层，SQLite 做状态与控制平面。**

***

# 二、对当前仓库的工程判断

当前 `src_data_download` 目录仍是典型的“脚本集合”形态，而不是“框架形态”。可见文件包括 `download_daily_2026.py`、`download_daily_basic_2026.py`、`download_moneyflow_2026.py`、`download_trade_date_generic.py`、`download_stock_basics.py`、`download_stk_mins_2026.py`、`update_raw_data.py`、`compact_raw_data.py`、`verify_2026.py` 等。README 已明确指出现有主干已经可用：`download_daily_2026.py` 和 `download_daily_basic_2026.py` 都是“按交易日拉取 → 分页 → 原子写 parquet → 写状态 → 并发执行”，而 `ts_download_utils.py` 已有 token 读取、重试、交易日历、分页抓取、原子落盘、状态清单、最大日期探测和进度条等通用能力。([GitHub](https://github.com/789453/tushare_data_download_and_compact/tree/main/src_data_download "https://github.com/789453/tushare_data_download_and_compact/tree/main/src_data_download"))

进一步看真实代码，`download_trade_date_generic.py` 的 `run()` 仍固定以 `trade_cal` 获取 `trade_dates`，统一使用单个 `_manifest.json`，固定 `limit = 6000`，并对每个交易日调用 `api(trade_date=d, limit=limit, offset=offset)`，然后把文件落成 `{trade_date}_o{offset}.parquet`；`update_raw_data.py` 仍通过 `if/elif` 硬编码分发 `daily/daily_basic/moneyflow/stk_limit/suspend_d`、`cyq_perf`、`stk_mins_*`，并在每个数据集更新后立刻执行 `compact_generic`；`compact_raw_data.py` 则按 `{name}_*parts` 搜索碎片目录，备份旧主文件为 `.bak_时间戳` 后再合并。`ts_download_utils.py` 中虽然已有 `retry_call`、`iter_trade_dates_yyyymmdd`、`paginated_fetch`、`StateManifest`、`get_parquet_max_date`、`compact_parquet_files_to_single`、`Progress` 等通用件，但它们还没有被提升为统一 runner/spec 体系。([GitHub](https://raw.githubusercontent.com/789453/tushare_data_download_and_compact/main/src_data_download/download_trade_date_generic.py "raw.githubusercontent.com"))

因此，这个仓库现在最真实的状态是：**下载骨架已经跑通，但抽象层级还停留在脚本层，README 和 tests 已经开始向框架层迁移，代码实现尚未跟上。** 这也是为什么你这次加指数、期货、期权、外汇、宏观后，必须正式引入 DuckDB + Parquet + SQLite 的三层架构，而不能继续“复制几个 `download_xxx_2026.py`”了。([GitHub](https://github.com/789453/tushare_data_download_and_compact "https://github.com/789453/tushare_data_download_and_compact"))

***

# 三、命名与数据域修正原则

你前面确认过的“命名问题”必须在这次改造里彻底修正。你上传的筛选清单里，第一组 `.CFX` 连续/主力/当月/次月/当季/下季代码被放在 `fx_obasic_full.parquet` 段里，但从 Tushare 文档和中金所/期货规则看，这类代码属于期货连续/映射域，应归入 `fut_mapping` / `fut_basic` / `fut_daily` 体系；而 `GBPUSD.FXCM`、`USDCNH.FXCM`、`USDJPY.FXCM`、`USOil.FXCM`、`XAGUSD.FXCM` 才属于 `fx_obasic` / `fx_daily` 域。`index_basic` 与 `opt_basic` 也应分别独立。 ([Tushare](https://tushare.pro/document/2?doc_id=189 "https://tushare.pro/document/2?doc_id=189"))

本次重构后，建议统一使用下面这些名称：

- `cffex_fut_mapping_selected`
- `cffex_fut_basic`
- `cffex_fut_daily`
- `fx_basic_selected`
- `fx_daily_selected`
- `index_basic_selected`
- `index_daily_selected`
- `index_dailybasic_supported`
- `cffex_opt_basic_full`
- `cffex_opt_daily`
- `macro_cn_gdp`
- `macro_cn_cpi`
- `macro_cn_ppi`

不要再沿用会误导数据域的文件名，例如把 `.CFX` 连续映射表命名成 `fx_obasic_full`。这一点不只是命名整洁问题，而是后续统一 API、统一主键、统一增量更新和统一验证规则是否能干净落地的基础。

***

# 四、最终项目架构形态

建议把项目最终收敛成下面这个结构。它与 README 已提出的 `core/ + adapters/ + datasets/ + jobs/ + tests/` 思路保持一致，但把 DuckDB、SQLite、配置、审计和 CLI 都纳入。README 中已经明确提出这样的方向，只是当前代码还没完全落地。([GitHub](https://github.com/789453/tushare_data_download_and_compact/blob/main/README.md "https://github.com/789453/tushare_data_download_and_compact/blob/main/README.md"))

```
tushare_data_download_and_compact/
├─ config/
│  ├─ settings.toml
│  ├─ logging.yaml
│  ├─ universe.yaml
│  └─ datasets/
│     ├─ stock.yaml
│     ├─ index.yaml
│     ├─ futures.yaml
│     ├─ options.yaml
│     ├─ macro.yaml
│     └─ fx.yaml
├─ data/
│  ├─ raw/                       # 原始 Parquet 分片与快照
│  │  ├─ stock/
│  │  ├─ index/
│  │  ├─ futures/
│  │  ├─ options/
│  │  ├─ macro/
│  │  └─ fx/
│  ├─ silver/                    # DuckDB 导出的标准 Parquet
│  ├─ catalog/                   # basic/universe 快照
│  ├─ audit/                     # verify report / dead letter / manifests
│  └─ meta/
│     ├─ control.sqlite3         # 控制平面
│     └─ warehouse.duckdb        # 分析仓库
├─ src_data_download/
│  ├─ core/
│  │  ├─ dataset_spec.py
│  │  ├─ task.py
│  │  ├─ task_builders.py
│  │  ├─ runner.py
│  │  ├─ state_store.py
│  │  ├─ lineage.py
│  │  ├─ parquet_sink.py
│  │  ├─ duckdb_store.py
│  │  ├─ sqlite_meta.py
│  │  ├─ rate_limiter.py
│  │  ├─ verify_rules.py
│  │  ├─ progress.py
│  │  └─ exceptions.py
│  ├─ adapters/
│  │  ├─ tushare_client.py
│  │  └─ calendars.py
│  ├─ datasets/
│  │  ├─ __init__.py
│  │  ├─ registry.py
│  │  ├─ stock_daily.py
│  │  ├─ stock_daily_basic.py
│  │  ├─ stock_moneyflow.py
│  │  ├─ stock_suspend.py
│  │  ├─ stock_limit.py
│  │  ├─ stock_basic.py
│  │  ├─ stock_minutes.py
│  │  ├─ index_basic_selected.py
│  │  ├─ index_daily_selected.py
│  │  ├─ index_dailybasic_supported.py
│  │  ├─ cffex_fut_basic.py
│  │  ├─ cffex_fut_mapping_selected.py
│  │  ├─ cffex_fut_daily_selected.py
│  │  ├─ cffex_opt_basic_full.py
│  │  ├─ cffex_opt_daily.py
│  │  ├─ fx_basic_selected.py
│  │  ├─ fx_daily_selected.py
│  │  ├─ macro_cn_gdp.py
│  │  ├─ macro_cn_cpi.py
│  │  └─ macro_cn_ppi.py
│  ├─ jobs/
│  │  ├─ bootstrap_history.py
│  │  ├─ catalog_refresh.py
│  │  ├─ update_incremental.py
│  │  ├─ compact_job.py
│  │  ├─ verify_job.py
│  │  ├─ smoke_job.py
│  │  └─ export_job.py
│  ├─ cli.py
│  └─ compat/
│     ├─ download_trade_date_generic.py
│     ├─ update_raw_data.py
│     └─ compact_raw_data.py
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  ├─ contract/
│  ├─ smoke/
│  └─ regression/
└─ pytest.ini

```

***

# 五、三层存储职责分工

## 5.1 Parquet：原始层与交换层

Parquet 继续承担三个职责：

第一，保存**raw 分片**。所有网络请求的返回结果先落 raw Parquet，不直接写入 DuckDB 正式事实表。这样可以保留原始响应痕迹，失败时也可以重放。DuckDB 官方明确支持直接读写 Parquet，并可直接对 Parquet 做 SQL 查询，因此 raw 用 Parquet 最合适。([DuckDB](https://duckdb.org/docs/current/data/parquet/overview.html?utm_source=chatgpt.com "Reading and Writing Parquet Files"))

第二，保存**快照类表**。例如 `fx_obasic`、`index_basic`、`fut_basic`、`opt_basic` 这类基础信息，应按抓取日期保留完整快照，写到 `data/raw/<asset>/<dataset>/snapshot_date=YYYYMMDD/part-000.parquet`。这类表不应该在 raw 层只留最新版本，否则 lineage 和审计能力会丢失。这个设计与你仓库 README 对快照类任务的建议一致。([GitHub](https://github.com/789453/tushare_data_download_and_compact/blob/main/README.md "https://github.com/789453/tushare_data_download_and_compact/blob/main/README.md"))

第三，保存**标准导出层**。DuckDB 中整理后的 silver 表应按数据集导出一份标准 Parquet 给后续策略研究、特征工程或其他下游系统使用。这样下游可以不直接耦合 `.duckdb` 文件，而只消费稳定 schema 的 Parquet。([DuckDB](https://duckdb.org/docs/current/data/parquet/overview.html?utm_source=chatgpt.com "Reading and Writing Parquet Files"))

## 5.2 DuckDB：事实层、整合层、验证层

DuckDB 负责：

- 从 raw Parquet 扫描数据；
- 用 `union_by_name` 思路容忍 schema 演进；
- 在 silver 层做去重、字段对齐、标准化；
- 用 `MERGE INTO` 执行增量 upsert；
- 做验证查询、缺口扫描、重复检查、指标统计；
- 把 silver 结果再导出为 Parquet。DuckDB 官方文档明确支持持久化数据库、Parquet 读写，以及 `MERGE INTO` 用于 upsert。([DuckDB](https://duckdb.org/docs/current/clients/python/overview.html?utm_source=chatgpt.com "Python API"))

DuckDB 不用来替代 raw 文件，而是充当**规范层/分析层**。也就是说：

- raw 是事实抓取记录；
- duckdb.silver 是规范事实表；
- 导出的 silver parquet 是对外交换层。

## 5.3 SQLite：控制平面

SQLite 只承担元数据控制，不存大事实表。建议它只存：

- `job_run`
- `task_run`
- `dataset_watermark`
- `file_manifest`
- `dataset_snapshot`
- `verify_run`
- `dead_letter`
- `catalog_state`

Python 标准库 `sqlite3` 适合这个场景；SQLite 的 WAL 模式更适合“多个 reader + 少量 writer”的控制平面；`INSERT ... ON CONFLICT DO UPDATE` 适合更新 watermark、task state、file manifest。([Python documentation](https://docs.python.org/3/library/sqlite3.html "https://docs.python.org/3/library/sqlite3.html"))

***

# 六、核心抽象与代码接口

## 6.1 `DatasetSpec`

整个工程的中心不再是脚本，而是 `DatasetSpec`。README 已明确提出这一步，并且现有 contract/unit tests 也已经在引用 `DatasetSpec`。([GitHub](https://github.com/789453/tushare_data_download_and_compact/blob/main/README.md "https://github.com/789453/tushare_data_download_and_compact/blob/main/README.md"))

建议定义如下：

```
from dataclasses import dataclass, field
from typing import Literal

FetchMode = Literal[
    "trade_date",
    "ts_code_range",
    "snapshot",
    "period_month",
    "period_quarter",
]

AssetClass = Literal["stock", "index", "futures", "options", "macro", "fx"]

@dataclass(frozen=True)
class DatasetSpec:
    name: str
    api_name: str
    asset_class: AssetClass
    fetch_mode: FetchMode

    pk_cols: tuple[str, ...]
    partition_cols: tuple[str, ...]
    date_col: str | None

    required_fields: tuple[str, ...] = ()
    optional_fields: tuple[str, ...] = ()
    fields: tuple[str, ...] | None = None

    limit: int = 2000
    supports_offset: bool = True
    supports_trade_cal: bool = False

    exchange_filter: str | None = None
    market_filter: str | None = None

    stable_before: str | None = None
    lookback_days: int = 0
    lookback_months: int = 0
    lookback_quarters: int = 0

    keep_snapshots: bool = False
    selected_codes: tuple[str, ...] = ()
    extra_params: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        ...

```

这里的重点不是字段多少，而是这几个约束必须进入 spec：

- `fetch_mode`
- `pk_cols`
- `date_col`
- `limit`
- `supports_offset`
- `stable_before`
- `lookback_*`
- `selected_codes`
- `keep_snapshots`

这样才能把“股票按交易日、指数按代码窗口、宏观按月份/季度、快照表按 snapshot”的差异固化到框架里，而不是散落在脚本里。这个方向与 README 中对 `DatasetSpec`、`TaskBuilder` 的建议一致。([GitHub](https://github.com/789453/tushare_data_download_and_compact/blob/main/README.md "https://github.com/789453/tushare_data_download_and_compact/blob/main/README.md"))

## 6.2 `Task`

一个 Task 对应一次幂等请求。tests 已经明确要求 task key 对 request\_params 的字典顺序不敏感，因此 `task_key` 必须基于 canonical JSON 生成。README 也给出了同样的建议。([GitHub](https://raw.githubusercontent.com/789453/tushare_data_download_and_compact/main/tests/unit/test_task_key.py "raw.githubusercontent.com"))

```
@dataclass(frozen=True)
class Task:
    spec: DatasetSpec
    request_params: dict[str, str]

    @property
    def params_hash(self) -> str:
        ...

    @property
    def task_key(self) -> str:
        ...

```

**统一规则：**

- `task_key = sha1(dataset_name + canonical_json(params))`
- `canonical_json` 必须 `sort_keys=True`
- 任何一个任务都必须能通过 `task_key` 在 SQLite 中唯一找到对应状态、输出文件、行数、重试次数和错误信息。

## 6.3 `TaskBuilder`

真正需要抽象的不是 `api_name`，而是任务构造器。README 已经把四类 builder 定义得很清楚，这里直接作为正式实现标准。([GitHub](https://github.com/789453/tushare_data_download_and_compact/blob/main/README.md "https://github.com/789453/tushare_data_download_and_compact/blob/main/README.md"))

### `TradeDateTaskBuilder`

适用：

- `daily`
- `daily_basic`
- `moneyflow`
- `stk_limit`
- `suspend_d`

逻辑：

- 通过交易日历取 `trade_date`
- 每个 `trade_date` 生成一个 task
- task 参数形如 `{"trade_date": "20260422"}`

### `CodeRangeTaskBuilder`

适用：

- `index_daily`
- `index_dailybasic`
- `fut_daily`
- `fut_mapping`
- `opt_daily`
- `fx_daily`

逻辑：

- 先获得 universe
- 每个 `ts_code + start_date + end_date` 生成一个 task
- 窗口粒度按数据集可配置：年/半年/季度

### `SnapshotTaskBuilder`

适用：

- `index_basic`
- `fut_basic`
- `opt_basic`
- `fx_obasic`
- `stock_basic`

逻辑：

- 一次全量或按交易所分片
- 以 `snapshot_date` 做目录分区
- 不走 trade\_cal

### `PeriodTaskBuilder`

适用：

- `cn_gdp`
- `cn_cpi`
- `cn_ppi`

逻辑：

- 季频生成 `start_q/end_q`
- 月频生成 `start_m/end_m`
- 初始化全量；增量回拉若干 period

## 6.4 `Runner`

`Runner` 是统一执行器。integration test 已经在使用一个 `FakePro + Runner + Task` 的模式，说明这条线是应该落地的。([GitHub](https://raw.githubusercontent.com/789453/tushare_data_download_and_compact/main/tests/integration/test_runner_fake_pro.py "raw.githubusercontent.com"))

```
class Runner:
    def __init__(
        self,
        project_root: Path,
        raw_root: Path,
        sqlite_meta: SQLiteMetaStore,
        duckdb_store: DuckDBStore,
        sink: ParquetSink,
        logger: logging.Logger,
        rate_limiter: GlobalRateLimiter,
    ):
        ...

    def run_dataset(
        self,
        pro,
        spec: DatasetSpec,
        tasks: list[Task],
        max_workers: int,
        overwrite: bool = False,
    ) -> list[TaskResult]:
        ...

    def run_tasks(
        self,
        pro,
        tasks: list[Task],
        max_workers: int,
        overwrite: bool = False,
    ) -> list[TaskResult]:
        ...

```

职责：

- 线程池执行；
- 分页抓取；
- 重试；
- sidecar lineage；
- 写 raw parquet；
- 更新 SQLite state；
- 发出 progress 事件；
- 失败任务进入 dead letter。

***

# 七、SQLite 控制平面设计

建议创建 `data/meta/control.sqlite3`，并在第一次启动时执行：

```
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;

```

WAL 可改善并发读写的实用性；这里不需要追求数据库服务器级别能力，只需要稳定记录元数据即可。([SQLite](https://www.sqlite.org/wal.html "https://www.sqlite.org/wal.html"))

建议表结构如下：

```
CREATE TABLE IF NOT EXISTS dataset_watermark (
    dataset_name      TEXT PRIMARY KEY,
    watermark_value   TEXT,
    watermark_col     TEXT,
    updated_at        TEXT NOT NULL,
    note              TEXT
);

CREATE TABLE IF NOT EXISTS job_run (
    job_id            TEXT PRIMARY KEY,
    job_type          TEXT NOT NULL,
    dataset_name      TEXT,
    started_at        TEXT NOT NULL,
    finished_at       TEXT,
    status            TEXT NOT NULL,
    total_tasks       INTEGER DEFAULT 0,
    done_tasks        INTEGER DEFAULT 0,
    failed_tasks      INTEGER DEFAULT 0,
    extra_json        TEXT
);

CREATE TABLE IF NOT EXISTS task_run (
    task_key          TEXT PRIMARY KEY,
    job_id            TEXT NOT NULL,
    dataset_name      TEXT NOT NULL,
    params_json       TEXT NOT NULL,
    params_hash       TEXT NOT NULL,
    started_at        TEXT,
    finished_at       TEXT,
    status            TEXT NOT NULL,
    rows_written      INTEGER DEFAULT 0,
    parquet_path      TEXT,
    retry_count       INTEGER DEFAULT 0,
    error_message     TEXT,
    FOREIGN KEY(job_id) REFERENCES job_run(job_id)
);

CREATE TABLE IF NOT EXISTS file_manifest (
    file_path         TEXT PRIMARY KEY,
    dataset_name      TEXT NOT NULL,
    task_key          TEXT,
    file_kind         TEXT NOT NULL,   -- raw_part/raw_snapshot/silver_export/verify_report
    row_count         INTEGER,
    file_size         INTEGER,
    file_hash         TEXT,
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS verify_run (
    verify_id         TEXT PRIMARY KEY,
    dataset_name      TEXT NOT NULL,
    started_at        TEXT NOT NULL,
    finished_at       TEXT,
    status            TEXT NOT NULL,
    duplicates_cnt    INTEGER DEFAULT 0,
    missing_cnt       INTEGER DEFAULT 0,
    invalid_cnt       INTEGER DEFAULT 0,
    report_json_path  TEXT,
    report_md_path    TEXT
);

CREATE TABLE IF NOT EXISTS dead_letter (
    dlq_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_name      TEXT NOT NULL,
    task_key          TEXT NOT NULL,
    params_json       TEXT NOT NULL,
    error_message     TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    replay_status     TEXT DEFAULT 'pending'
);

```

所有更新操作使用 SQLite UPSERT，例如：

```
INSERT INTO dataset_watermark(dataset_name, watermark_value, watermark_col, updated_at)
VALUES (?, ?, ?, ?)
ON CONFLICT(dataset_name) DO UPDATE SET
  watermark_value = excluded.watermark_value,
  watermark_col   = excluded.watermark_col,
  updated_at      = excluded.updated_at;

```

这样做的好处是：控制平面不会再依赖一个脆弱的 `_manifest.json`，而是有真正可查询、可回放、可统计的状态库。`download_trade_date_generic.py` 当前的 `StateManifest` 适合作为过渡兼容层，但不应该继续当主状态源。([GitHub](https://raw.githubusercontent.com/789453/tushare_data_download_and_compact/main/src_data_download/ts_download_utils.py "raw.githubusercontent.com"))

***

# 八、DuckDB 仓库设计

建议使用一个持久化的 `data/meta/warehouse.duckdb` 文件。DuckDB 官方文档明确支持通过指定文件路径创建持久数据库。([DuckDB Blobs](https://blobs.duckdb.org/docs/duckdb-docs.pdf "https://blobs.duckdb.org/docs/duckdb-docs.pdf"))

建议 schema：

```
CREATE SCHEMA IF NOT EXISTS raw_ext;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS audit;

```

## 8.1 raw\_ext

不真正存表，而是用 view 或临时 relation 指向 raw parquet：

- `raw_ext.stock_daily_parts`
- `raw_ext.index_daily_parts`
- `raw_ext.cffex_fut_mapping_parts`
- `raw_ext.cffex_opt_basic_snapshots`
- `raw_ext.macro_cn_gdp_parts`

## 8.2 silver

存标准事实表/维表：

- `silver.fact_stock_daily`
- `silver.fact_stock_daily_basic`
- `silver.fact_index_daily`
- `silver.fact_index_dailybasic`
- `silver.dim_index_basic`
- `silver.dim_fut_contract`
- `silver.fact_fut_daily`
- `silver.bridge_fut_mapping`
- `silver.dim_option_contract`
- `silver.fact_option_daily`
- `silver.dim_fx_symbol`
- `silver.fact_fx_daily`
- `silver.fact_macro_gdp`
- `silver.fact_macro_cpi`
- `silver.fact_macro_ppi`

## 8.3 写入策略

- 初始化：`CREATE TABLE AS SELECT ... FROM read_parquet(...)`
- 增量：`MERGE INTO silver.xxx USING stage ON pk ... WHEN MATCHED THEN UPDATE WHEN NOT MATCHED THEN INSERT`
- 导出：`COPY (SELECT * FROM silver.xxx) TO '...parquet' (FORMAT parquet)`

DuckDB 的 `MERGE INTO` 正是这里最关键的升级点：你不必继续“先把所有旧 parquet 读成 pandas，再 drop\_duplicates，再整体重写”。你可以先把 raw part 读入 DuckDB stage，然后做真正意义上的增量 merge。([DuckDB](https://duckdb.org/docs/current/sql/statements/merge_into.html "https://duckdb.org/docs/current/sql/statements/merge_into.html"))

***

# 九、数据集注册表设计

README 已经按 `fetch_mode` 把各类数据集梳理清楚了，下面我把它正式收敛成你这次要实现的第一批 registry。([GitHub](https://github.com/789453/tushare_data_download_and_compact/blob/main/README.md "https://github.com/789453/tushare_data_download_and_compact/blob/main/README.md"))

## 9.1 股票（保留现有主线）

- `stock_daily` → `daily` → `trade_date`
- `stock_daily_basic` → `daily_basic` → `trade_date`
- `stock_moneyflow` → `moneyflow` → `trade_date`
- `stock_limit` → `stk_limit` → `trade_date`
- `stock_suspend` → `suspend_d` → `trade_date`

这部分直接迁入新框架，不改数据语义。

## 9.2 指数

- `index_basic_selected` → `index_basic` → `snapshot`
- `index_daily_selected` → `index_daily` → `ts_code_range`
- `index_dailybasic_supported` → `index_dailybasic` → `ts_code_range`

`index_daily` 单次最多 8000 行，适合按 `ts_code + 时间窗口`；`index_dailybasic` 只覆盖少数大盘指数，不是所有指数都可用，因此必须单独维护支持池。([Tushare](https://tushare.pro/document/2?doc_id=95 "https://tushare.pro/document/2?doc_id=95"))

## 9.3 CFFEX 期货

- `cffex_fut_basic` → `fut_basic(exchange='CFFEX')` → `snapshot`
- `cffex_fut_mapping_selected` → `fut_mapping` → `ts_code_range`
- `cffex_fut_daily_selected` → `fut_daily` → `ts_code_range`

Tushare 期货文档明确区分了 `fut_basic`（合约信息）、`fut_daily`（日线）、`fut_mapping`（主力/连续到月合约映射）；并明确给出了 CFFEX 连续代码的命名规则，例如 `IF.CFX`、`IFL.CFX`、`IFL1.CFX`、`IFL2.CFX`、`IFL3.CFX`。你的上传白名单第一段应全部归入这个域。 ([Tushare](https://tushare.pro/document/2?doc_id=135 "https://tushare.pro/document/2?doc_id=135"))

## 9.4 CFFEX 期权

- `cffex_opt_basic_full` → `opt_basic(exchange='CFFEX')` → `snapshot`
- `cffex_opt_daily` → `opt_daily(exchange='CFFEX')` → `trade_date` 或 `ts_code_range`

`opt_basic` 是合约维表，建议保留全量快照；`opt_daily` 单次最大 15000 条，既可以按交易日，也可以按代码窗口，但为了统一你当前“10 个 dataset 并发 + 每 dataset 10 个 task”的模型，建议实现为 `CodeRangeTaskBuilder`，并在日更模式下允许切成“最近 N 天 + 代码桶”。([Tushare](https://tushare.pro/document/2?doc_id=158 "https://tushare.pro/document/2?doc_id=158"))

## 9.5 外汇

- `fx_basic_selected` → `fx_obasic` → `snapshot`
- `fx_daily_selected` → `fx_daily` → `ts_code_range`

`fx_obasic` 当前是 FXCM 交易商海外外汇/CFD/商品/金属等基础信息，一次可全量提取；你的第二组白名单 `GBPUSD.FXCM`、`USDCNH.FXCM`、`USDJPY.FXCM`、`USOil.FXCM`、`XAGUSD.FXCM` 应从这张快照中本地筛出。README 也提示 `fx_daily.trade_date` 是 GMT，需要显式做时区适配。 ([Tushare](https://tushare.pro/document/2?doc_id=178 "https://tushare.pro/document/2?doc_id=178"))

## 9.6 宏观

- `macro_cn_gdp` → `cn_gdp` → `period_quarter`
- `macro_cn_cpi` → `cn_cpi` → `period_month`
- `macro_cn_ppi` → `cn_ppi` → `period_month`

这三类一次就能拿完历史，全量初始化和滚动回拉都很适合用 PeriodTaskBuilder。官方文档也明确给出了 `start_q/end_q` 与 `start_m/end_m` 参数形式。([Tushare](https://tushare.pro/document/2?doc_id=227 "https://tushare.pro/document/2?doc_id=227"))

***

# 十、Universe 与配置文件

不要把白名单直接写死在数据集 Python 文件里。README 已经给了配置化方向。([GitHub](https://github.com/789453/tushare_data_download_and_compact/blob/main/README.md "https://github.com/789453/tushare_data_download_and_compact/blob/main/README.md"))

建议建立 `config/universe.yaml`：

```
indices_selected:
  - 000001.SH
  - 399001.SZ
  - 399300.SZ
  - 399006.SZ
  - 000699.SH
  - 399852.SZ
  - 000905.SH
  - 399405.SZ
  - 399406.SZ
  - 399407.SZ
  - 399408.SZ
  - 399409.SZ
  - CN5140.CNI
  - CN5141.CNI
  - CN6138.CNI
  - CN6139.CNI
  - CN6140.CNI
  - CN6141.CNI
  - CSPSADRP.CI
  - CN2372.CNI
  - CN2373.CNI
  - CN2374.CNI
  - CN2375.CNI
  - CN2376.CNI
  - CN2377.CNI
  - CN2602.CNI
  - CN2604.CNI
  - CN2626.CNI
  - CN2627.CNI

cffex_mapping_selected:
  - TSL.CFX
  - TSL1.CFX
  - TSL2.CFX
  - IF.CFX
  - IH.CFX
  - IC.CFX
  - IM.CFX
  - IML.CFX
  - IML1.CFX
  - IML2.CFX
  - IFL.CFX
  - IFL1.CFX
  - IFL2.CFX
  - IFL3.CFX
  - ICL.CFX
  - ICL1.CFX
  - ICL2.CFX
  - ICL3.CFX
  - IHL.CFX
  - IHL1.CFX
  - IHL2.CFX
  - IHL3.CFX
  - IML3.CFX

fx_selected:
  - GBPUSD.FXCM
  - USDCNH.FXCM
  - USDJPY.FXCM
  - USOil.FXCM
  - XAGUSD.FXCM

```

`opt_basic_cffex` 不设白名单，直接全量。以上集合正是你上传要求的可机器消费版。

***

# 十一、增量更新与稳定区策略

你特别强调：不要把文件拆得太细，要支持自动更新，同时认为 2016 年 3 月以前大体稳定。这个要求非常适合三层架构。

## 11.1 统一原则

- **历史初始化**：全量抓一次，进入 raw + silver
- **日常增量**：只更新非稳定区，并做滚动回看
- **验证后合并**：raw part 不直接等于主文件，要先验证再 merge
- **不按天生成无穷多主文件**：raw 可分片，silver 维持稳定表

## 11.2 建议水位策略

### 股票/指数/期货/期权/外汇日线

- `stable_before = 20160301`
- 常规更新：
  - `start = max(watermark - lookback_days, stable_before)`
  - `lookback_days = 30` 默认
- 每周一次深回刷：
  - `lookback_days = 120`

### 宏观

- `macro_cn_gdp`: 每次回拉最近 8 个季度
- `macro_cn_cpi` / `macro_cn_ppi`: 每次回拉最近 24 个月

这与 README 对宏观回拉最近若干季度/月的建议一致，也符合 Tushare 接口“单次基本可以提完”的特性。([GitHub](https://github.com/789453/tushare_data_download_and_compact/blob/main/README.md "https://github.com/789453/tushare_data_download_and_compact/blob/main/README.md"))

## 11.3 快照类

- `index_basic` / `fut_basic` / `opt_basic` / `fx_obasic`
- 每次全量抓取
- raw 层保留快照
- silver 层只保留 `is_latest=1` 当前版本，或做 SCD2（第二阶段再上）

## 11.4 你当前旧逻辑的替换

当前 `update_raw_data.py` 的逻辑是：从主 parquet 找最大日期，然后从这个日期继续跑。这必须升级为“watermark + lookback”模型，不再直接依赖“主文件最大日期”这一种判据。([GitHub](https://raw.githubusercontent.com/789453/tushare_data_download_and_compact/main/src_data_download/update_raw_data.py "raw.githubusercontent.com"))

***

# 十二、并发、限流、下载稳健性

当前脚本使用 `ThreadPoolExecutor`。这可以保留，不必强行改 `asyncio`。原因不是“asyncio 不行”，而是当前 Tushare SDK 调用方式本身就是阻塞式，线程池更直接。现有代码也已经是这个模型。([GitHub](https://raw.githubusercontent.com/789453/tushare_data_download_and_compact/main/src_data_download/download_trade_date_generic.py "raw.githubusercontent.com"))

但要从“脚本内线程池”升级为“两级并发 + 全局限流”：

- **dataset-level workers = 10**
- **task-level workers = 10**
- **global rate limiter** 以 `api_name` 为粒度配置

建议 `config/settings.toml`：

```
[concurrency]
max_dataset_workers = 10
default_task_workers = 10

[rate_limit.daily]
rpm = 120

[rate_limit.index_daily]
rpm = 60

[rate_limit.fut_basic]
rpm = 80

[rate_limit.fut_daily]
rpm = 120

[rate_limit.fut_mapping]
rpm = 60

[rate_limit.opt_daily]
rpm = 60

[rate_limit.macro_default]
rpm = 30

```

这里的具体数值不是死规则，而是可配置上限。Tushare 官方文档确实明确给出了一些期货接口的每分钟频次示例，也说明 `index_daily`、`opt_daily` 等有单次条数和权限/流控约束，所以并发必须叠加限流器。([Tushare](https://tushare.pro/document/2?doc_id=134 "https://tushare.pro/document/2?doc_id=134"))

***

# 十三、文件落盘与 lineage 规则

每个 raw part 必须同时产生 sidecar metadata，而不是只留 parquet。

建议 raw 落盘命名：

```
data/raw/index/index_daily_selected/ts_code=399300.SZ/year=2024/399300.SH_20240101_20241231_0001.parquet
data/raw/index/index_daily_selected/ts_code=399300.SZ/year=2024/399300.SH_20240101_20241231_0001.parquet.meta.json

```

sidecar 内容建议：

```
{
  "dataset_name": "index_daily_selected",
  "task_key": "sha1...",
  "params_json": {"ts_code":"399300.SZ","start_date":"20240101","end_date":"20241231"},
  "api_name": "index_daily",
  "rows": 253,
  "columns": ["ts_code","trade_date","close","open","high","low", "..."],
  "fetched_at": "2026-04-22T11:32:11+08:00",
  "source": "tushare",
  "part_seq": 1,
  "file_hash": "sha256...",
  "status": "done"
}

```

这条规则要统一到所有数据集。这样验证和审计时不再靠“猜文件名”，而是靠明确的 manifest + sidecar + SQLite file\_manifest。

***

# 十四、日志与进度展示

当前仓库已经有一个简单 `Progress` 类，但需要升级成标准日志系统。README 也把“进度条、结果展示、验证报告”列为框架能力之一；Python 官方 `logging` 模块就是通用日志设施，而 Rich 的 `Progress` 能很好地展示多任务并发进度。([GitHub](https://github.com/789453/tushare_data_download_and_compact "https://github.com/789453/tushare_data_download_and_compact"))

建议：

## 14.1 日志

使用 Python `logging`，按 logger namespace 分层：

- `tdc.cli`
- `tdc.runner`
- `tdc.dataset.index_daily`
- `tdc.dataset.fut_mapping`
- `tdc.verify`
- `tdc.compact`

输出：

- 控制台：INFO
- 文件：DEBUG
- 审计日志：JSON lines

建议日志文件：

- `logs/app.log`
- `logs/error.log`
- `logs/jobs/<job_id>.jsonl`

## 14.2 进度条

控制台使用 Rich `Progress`：

- 顶层展示 dataset 任务总进度
- 子层展示当前 dataset 内 task 进度
- 可显示已完成数、失败数、累计行数、速率、ETA

Rich 文档明确支持多任务进度展示，适合线程或进程并发场景。([Rich Documentation](https://rich.readthedocs.io/en/latest/progress.html "https://rich.readthedocs.io/en/latest/progress.html"))

## 14.3 结果报告

每次 job 结束输出：

- `job_summary.json`
- `job_summary.md`

至少包括：

- dataset
- started\_at / finished\_at
- tasks\_total / success / failed
- rows\_written
- raw\_files
- silver\_tables\_updated
- verify\_status

***

# 十五、测试体系

这是必须保留并扩充的。当前仓库已经有 `pytest.ini`，并把 `tests` 设为测试目录，文件名模式为 `test_*.py`；同时 `tests/unit`、`tests/integration`、`tests/contract` 已经存在。([GitHub](https://github.com/789453/tushare_data_download_and_compact/blob/main/pytest.ini "tushare_data_download_and_compact/pytest.ini at main · 789453/tushare_data_download_and_compact · GitHub"))

## 15.1 当前测试现状

现有测试已经在表达正确方向：

- `test_dataset_spec.py`：校验 `DatasetSpec.validate()`
- `test_task_key.py`：校验 task key 对参数字典顺序稳定
- `test_runner_fake_pro.py`：用 FakePro 测 Runner 写 parquet 和 sidecar
- `test_dataset_specs_contract.py`：遍历 `src_data_download.datasets` 中的 `SPEC` 并做契约校验\
  但这些测试引用的 `src_data_download.core.*` 和 `src_data_download.datasets.*` 路径，与当前 `src_data_download` 可见目录不一致，这正说明主实现需要向这些测试对齐，而不是把测试删掉。([GitHub](https://raw.githubusercontent.com/789453/tushare_data_download_and_compact/main/tests/unit/test_dataset_spec.py "raw.githubusercontent.com"))

## 15.2 改造后的测试分层

### unit

- `DatasetSpec.validate`
- `Task.task_key`
- `TaskBuilder` 各种边界
- `SQLiteMetaStore` upsert / resume
- `DuckDBStore.merge_incremental`
- `ParquetSink.write_with_sidecar`
- `get_watermark`
- `timezone adapter`

### contract

- 所有 `datasets/*.py` 中的 `SPEC` 均可 `validate()`
- 所有 `pk_cols` 必属 required/optional fields
- 所有 `fetch_mode` 与参数 builder 匹配
- 所有 `selected_codes` 如存在则非空且去重

### integration

- FakePro 跑完整 runner
- SQLite + DuckDB + Parquet 联调
- raw → silver → export 全链路

### smoke

真实 Tushare 小样本：

- `index_daily_selected`: `399300.SZ` 最近 5 日
- `cffex_fut_mapping_selected`: `IF.CFX` 最近 5 日
- `cffex_opt_basic_full`: `exchange='CFFEX'`
- `fx_daily_selected`: `USDCNH.FXCM` 最近 10 日
- `macro_cn_gdp`: 最近 4 季度

### regression

保留小型 golden parquet / golden duckdb snapshot，对比：

- row count
- pk unique count
- max date
- column set
- checksum

这也与 README 对 unit / contract / smoke / regression 的分层建议一致。([GitHub](https://github.com/789453/tushare_data_download_and_compact/blob/main/README.md "https://github.com/789453/tushare_data_download_and_compact/blob/main/README.md"))

***

# 十六、关键文件逐一改造方案

下面是最重要的“文件级别改造清单”。

## 16.1 `src_data_download/ts_download_utils.py`

**处理方式：拆分重构，保留少量兼容函数。**

当前它同时承担重试、交易日历、parquet 写入、manifest、最大日期探测、compact、progress 等多种职责。([GitHub](https://raw.githubusercontent.com/789453/tushare_data_download_and_compact/main/src_data_download/ts_download_utils.py "raw.githubusercontent.com"))

### 保留到兼容层的函数

- `get_tushare_token`
- `load_tushare_pro`
- `retry_call`
- `write_parquet_atomic`

### 迁移出去

- `StateManifest` → `core/sqlite_meta.py`
- `Progress` → `core/progress.py`
- `compact_parquet_files_to_single` → `core/duckdb_store.py`
- `get_parquet_max_date` → `core/watermark.py`
- `iter_trade_dates_yyyymmdd` → `adapters/calendars.py`

### 新要求

- 不再把所有 `int64/int32/float64` 一律转成 `float32`
- 去重主键不再默认写死为 `["ts_code","trade_date"]`
- 工具函数必须无副作用、可单测

## 16.2 `src_data_download/download_trade_date_generic.py`

**处理方式：保留 compat wrapper，主逻辑迁入** **`Runner + TradeDateTaskBuilder`。**

当前问题是它把任务模型写死成 `trade_date + offset`。([GitHub](https://raw.githubusercontent.com/789453/tushare_data_download_and_compact/main/src_data_download/download_trade_date_generic.py "raw.githubusercontent.com"))

### 改法

- 文件迁到 `compat/download_trade_date_generic.py`
- 仅保留：
  - 解析旧参数
  - 构造相应的 `DatasetSpec`
  - 调用新 `Runner.run_dataset()`

### 不再保留的逻辑

- `_manifest.json` 本地状态
- 写死 `limit=6000`
- 直接 `api(trade_date=d...)`
- 直接以 out\_dir 作为状态依据

## 16.3 `src_data_download/update_raw_data.py`

**处理方式：完全重写，变成 compat wrapper；真正新入口是** **`jobs/update_incremental.py`。**

当前它是 if/elif 分发器。([GitHub](https://raw.githubusercontent.com/789453/tushare_data_download_and_compact/main/src_data_download/update_raw_data.py "raw.githubusercontent.com"))

### 新实现

- 解析 `--datasets`
- 从 `datasets.registry` 取 spec
- 从 SQLite 取 watermark
- 调 `TaskBuilder`
- 调 `Runner`
- 结束后触发 `compact_job` 与 `verify_job`

### 删除旧逻辑

- `main_file = raw_dir / f"{name}.parquet"` 这种主文件推断
- 直接 `max_d = get_parquet_max_date(main_file)` 的单一续传逻辑
- 每个 dataset 下载完立刻粗暴 compact

## 16.4 `src_data_download/compact_raw_data.py`

**处理方式：兼容入口保留，核心逻辑改成 DuckDB merge/export。**

当前它通过搜索 `{name}_*parts`，备份旧主文件，然后把旧主文件和 parts 一起重新合成一个 parquet。([GitHub](https://raw.githubusercontent.com/789453/tushare_data_download_and_compact/main/src_data_download/compact_raw_data.py "raw.githubusercontent.com"))

### 新实现

- `jobs/compact_job.py`
- 从 SQLite `file_manifest` 取本次待合并 raw parts
- DuckDB 读取 raw parts → stage
- 按 `DatasetSpec.pk_cols` 做 `MERGE INTO silver.table`
- 导出 silver parquet
- 记录 export 文件到 `file_manifest`

### 兼容入口

旧 `compact_raw_data.py` 只负责：

```
from src_data_download.jobs.compact_job import main

```

## 16.5 `src_data_download/download_daily_2026.py` / `download_daily_basic_2026.py`

**处理方式：删除业务逻辑，仅保留 wrapper 或直接下线。**

这两个脚本当前高度重复。README 也已点出这一点。([GitHub](https://github.com/789453/tushare_data_download_and_compact "https://github.com/789453/tushare_data_download_and_compact"))

### 迁移目标

- `datasets/stock_daily.py`
- `datasets/stock_daily_basic.py`

### wrapper 模式

如果必须保留历史命令：

```
python src_data_download/download_daily_2026.py --start-date ...

```

则内部只组装 spec 并调用 CLI。

## 16.6 `tests/*`

**处理方式：保留并扩充，不删。**

### 立刻要做的事

- 让 `src_data_download/core/...` 与 `src_data_download/datasets/...` 真正落地
- 让当前已有 tests 先跑通
- 再加 smoke/regression

***

# 十七、CLI 统一接口

最终统一为一个入口：

```
python -m src_data_download.cli catalog-refresh --datasets index_basic_selected,cffex_fut_basic,fx_basic_selected
python -m src_data_download.cli bootstrap-history --datasets index_daily_selected,cffex_fut_mapping_selected,cffex_opt_basic_full,macro_cn_gdp
python -m src_data_download.cli update-incremental --datasets all_core --max-dataset-workers 10 --max-task-workers 10
python -m src_data_download.cli compact --datasets all_core
python -m src_data_download.cli verify --datasets all_core
python -m src_data_download.cli smoke --datasets cffex_opt_basic_full,macro_cn_cpi

```

Python API：

```
from src_data_download.datasets.registry import REGISTRY
from src_data_download.jobs.update_incremental import run_incremental

run_incremental(
    dataset_specs=[
        REGISTRY["index_daily_selected"],
        REGISTRY["cffex_fut_mapping_selected"],
        REGISTRY["cffex_opt_basic_full"],
        REGISTRY["fx_daily_selected"],
        REGISTRY["macro_cn_gdp"],
    ],
    max_dataset_workers=10,
    max_task_workers=10,
)

```

***

# 十八、推荐实施顺序

## Phase 1：搭骨架

1. 建 `core/`
2. 建 `datasets/registry.py`
3. 落 `SQLiteMetaStore`
4. 落 `DuckDBStore`
5. 跑通 `stock_daily`

## Phase 2：迁股票主线

1. `daily`
2. `daily_basic`
3. `moneyflow`
4. `stk_limit`
5. `suspend_d`

## Phase 3：接你这次新增的资产

1. `index_basic_selected`
2. `index_daily_selected`
3. `index_dailybasic_supported`
4. `cffex_fut_basic`
5. `cffex_fut_mapping_selected`
6. `cffex_opt_basic_full`
7. `fx_basic_selected`
8. `fx_daily_selected`
9. `macro_cn_gdp`
10. `macro_cn_cpi`
11. `macro_cn_ppi`

## Phase 4：补自动化

1. `compact_job`
2. `verify_job`
3. `smoke_job`
4. 回归样本
5. 日常 cron / 计划任务

***

# 十九、最终定版原则

这次改造定版时，要满足下面 8 条，否则不要认为“完成”：

1. `src_data_download/core`、`src_data_download/datasets`、`src_data_download/jobs` 真实存在，且当前 tests 能跑。现有 tests 已经在要求这些模块存在。([GitHub](https://raw.githubusercontent.com/789453/tushare_data_download_and_compact/main/tests/unit/test_dataset_spec.py "raw.githubusercontent.com"))
2. `download_trade_date_generic.py`、`update_raw_data.py`、`compact_raw_data.py` 仅作为 compat，不再承载主逻辑。当前主逻辑仍集中在这些文件里。([GitHub](https://raw.githubusercontent.com/789453/tushare_data_download_and_compact/main/src_data_download/download_trade_date_generic.py "raw.githubusercontent.com"))
3. raw 全部先落 Parquet，silver 全部走 DuckDB merge，再统一导出标准 Parquet。DuckDB 对 Parquet 扫描和写出都已是官方支持路径。([DuckDB](https://duckdb.org/docs/current/data/parquet/overview.html?utm_source=chatgpt.com "Reading and Writing Parquet Files"))
4. 所有 task 状态、水位、文件清单、verify 索引都入 SQLite，不再依赖 `_manifest.json` 为主状态源。SQLite 的 `sqlite3`、WAL、UPSERT 已足够支持控制平面。([Python documentation](https://docs.python.org/3/library/sqlite3.html "https://docs.python.org/3/library/sqlite3.html"))
5. 你的命名修正必须落地：`.CFX` 连续映射不再挂在 FX 域名下。
6. `index_dailybasic` 只针对官方支持池运行，不能误以为适用于全部指数。([Tushare](https://tushare.pro/document/2?doc_id=128 "https://tushare.pro/document/2?doc_id=128"))
7. 宏观必须走 `period_month/period_quarter`，不允许再被套进 trade\_date 下载器。Tushare 官方已经明确了 `cn_gdp`、`cn_cpi`、`cn_ppi` 的 period 参数形态。([Tushare](https://tushare.pro/document/2?doc_id=227 "https://tushare.pro/document/2?doc_id=227"))
8. 日志、进度条、verify report、smoke test 都必须是正式模块，而不是“开发期间的辅助脚本”。Python logging 和 Rich progress 都能直接支撑这个要求。([Python documentation](https://docs.python.org/3/library/logging.html "https://docs.python.org/3/library/logging.html"))

这份文档可以直接作为重构蓝图使用。下一步最合适的动作，不是继续讨论概念，而是按这份文档先落第一批真实文件：`dataset_spec.py`、`task.py`、`task_builders.py`、`sqlite_meta.py`、`duckdb_store.py`、`runner.py`、`datasets/registry.py`，然后先把 `stock_daily` 和 `index_basic_selected` 跑通。
