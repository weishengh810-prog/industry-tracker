# 行业发展势头监测系统

这是一个可配置、可降级的 Python MVP，用于每天采集公开新闻、政策标题和 ETF/指数代理行情，生成统一行业指标长表、行业发展势头排名、Markdown 报告和柱状图。

首版覆盖 12 个行业：

人工智能、半导体、新能源汽车、储能、机器人、低空经济、跨境电商、医药健康、消费零售、物流供应链、旅游、网络安全。

> ETF/指数只用于观察资本市场预期，是代理指标，不代表行业真实市场规模、收入或利润，也不构成投资建议。

## 项目结构

```text
industry-tracker/
├── config/
│   ├── industries.json
│   └── sources.json
├── data/
│   ├── raw/
│   ├── processed/
│   └── samples/
├── reports/
├── charts/
├── logs/
├── scripts/
│   ├── common.py
│   ├── content_collector.py
│   ├── fetch_news.py
│   ├── fetch_policy.py
│   ├── fetch_market.py
│   ├── build_dataset.py
│   ├── score_industries.py
│   ├── generate_report.py
│   └── run_pipeline.py
├── tests/
├── run_all.ps1
├── run_all.sh
└── requirements.txt
```

三个采集器彼此独立，只通过 CSV 文件与后续处理模块连接。新闻或政策来源失败、行情下载失败、行业没有市场代理时，不会中断其他采集器。

## 安装

要求 Python 3.10 或更高版本。

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Linux / macOS

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 运行

### 离线演示

离线模式完全不访问网络，使用 `data/samples/` 中的固定样例数据，适合首次验证和作品集演示。

Windows：

```powershell
.\run_all.ps1 --offline
```

Linux / macOS：

```bash
./run_all.sh --offline
```

通用 Python 入口：

```bash
python scripts/run_pipeline.py --offline
```

### 在线运行

```bash
python scripts/run_pipeline.py
```

默认启用样例回退。某一类在线数据完全不可用时，该采集器使用离线样例并标记 `sample`，流水线继续运行。

禁用样例回退：

```bash
python scripts/run_pipeline.py --no-fallback-samples
```

禁用后，失败维度写入 `source_error`，评分阶段将其视为缺失，而不是 0 分。

### 独立运行脚本

```bash
python scripts/fetch_news.py
python scripts/fetch_policy.py
python scripts/fetch_market.py
python scripts/build_dataset.py
python scripts/score_industries.py
python scripts/generate_report.py
```

采集器也可以单独使用离线模式：

```bash
python scripts/fetch_news.py --offline
python scripts/fetch_policy.py --offline
python scripts/fetch_market.py --offline
```

所有脚本通过自身位置解析项目目录，不要求从固定当前目录启动。

## 输出

完整流水线生成：

```text
data/raw/news_daily.csv
data/raw/policy_daily.csv
data/raw/market_daily.csv
data/processed/industry_metrics_long.csv
reports/industry_score.csv
reports/industry_report.md
charts/industry_score_bar.png
logs/industry_tracker.log
logs/error.log
```

统一长表固定字段：

| 字段 | 说明 |
| --- | --- |
| `industry` | 行业名称 |
| `date` | 指标日期，ISO 8601 格式 |
| `metric` | `news_heat`、`policy_heat` 或 `market_return_3m` |
| `value` | 指标值；缺失时为空 |
| `source` | RSS、政策网页或代理标的 |
| `status` | 数据状态 |

数据状态：

| 状态 | 说明 |
| --- | --- |
| `ok` | 在线数据成功 |
| `sample` | 使用离线样例 |
| `no_match` | 来源成功，但没有匹配行业关键词 |
| `missing_config` | 行业没有配置合理的市场代理 |
| `source_error` | 来源请求、解析或下载失败 |
| `insufficient_data` | 行情有效样本不足 |

## 数据源

### 新闻

`config/sources.json` 中的 `news` 列表配置公开 RSS/Atom。标题通过行业关键词匹配，并按行业和日期去重计数。

### 政策

`policy` 列表支持：

- `rss`：RSS/Atom 来源。
- `html`：公开列表页，需要配置 `item_selector`、`title_selector` 和 `date_selector`。

政策网页可能改版。单个选择器失效只影响该来源，错误会写入日志。

### 市场代理

`config/industries.json` 中的 `market_proxy` 配置 yfinance ticker 和显示名称。近 3 个月表现按可获得区间的首尾收盘价计算：

```text
market_return_3m = 最新收盘价 / 区间首个收盘价 - 1
```

中国新兴行业没有合理 ETF/指数时，`market_proxy` 应设为 `null`。系统会写入 `missing_config`，不会尝试下载或中断流程。

## 评分方法

三个指标分别按当期行业截面百分位映射到 0-100 分：

```text
综合分 =
新闻热度分 × 40%
+ 市场代理表现分 × 30%
+ 政策热度分 × 30%
```

`ok`、`sample` 和 `no_match` 可以参与评分；`missing_config`、`source_error` 和 `insufficient_data` 视为缺失。

缺少某个维度时，只在可用维度上按原权重比例重新归一化。例如市场代理缺失但新闻和政策可用时，可用权重为 70%，综合分由新闻和政策分按 40:30 计算。评分 CSV 同时保留：

- 原始指标值
- 分项百分位分
- 综合分和排名
- 可用权重
- 缺失指标
- 各指标数据状态

## 定时运行

### Linux crontab

每天北京时间 07:30 运行：

```cron
30 7 * * * cd /opt/industry-tracker && /opt/industry-tracker/.venv/bin/python scripts/run_pipeline.py >> logs/cron.log 2>&1
```

编辑任务：

```bash
crontab -e
```

服务器时区不是 `Asia/Shanghai` 时，应先换算执行时间或设置服务器时区。

### Windows 任务计划程序

程序填写 PowerShell：

```text
powershell.exe
```

参数：

```text
-ExecutionPolicy Bypass -File "C:\path\to\industry-tracker\run_all.ps1"
```

“起始于”填写项目目录。离线定时演示可在参数末尾增加 `--offline`。

## 测试

```bash
python -m pytest -v
```

测试覆盖关键词去重、空市场代理、来源失败回退、长表契约、缺失权重重归一化、报告免责声明和离线端到端运行。

## 配置扩展

### 新增行业

在 `config/industries.json` 添加行业名称、关键词和可选 `market_proxy`。没有可靠代理时保留 `null`，不要为了凑齐指标使用相关性很弱的 ETF。

### 新增来源

在 `config/sources.json` 对应列表中添加公开 RSS 或网页来源。不要添加需要登录、验证码或绕过访问控制的网站。

### 新增指标

后续可以扩展国家统计局、海关进出口、世界银行、OECD、搜索趋势、招聘公开报告和政策文本分析。新增采集器仍应输出相同长表字段，并在评分模型中显式增加权重和缺失处理规则。

## 使用限制

- 新闻和政策热度反映关注度，不等同于产业收入或盈利增长。
- 关键词法可能出现同义词遗漏、语境误判和转载重复。
- 免费网页与 RSS 可能改版、限流或暂时不可用。
- 离线样例只用于验证流程，不能用于现实投资、政策或经营决策。
