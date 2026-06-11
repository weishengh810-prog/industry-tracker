# 行业发展势头监测系统设计

## 1. 目标与首版范围

构建一个可配置、可降级的 Python MVP，按日采集 12 个中国相关行业的公开新闻、政策信息和 ETF/指数代理行情，统一整理为长表，计算行业发展势头评分，并输出 CSV、Markdown 报告和柱状图。

首版行业：

1. 人工智能
2. 半导体
3. 新能源汽车
4. 储能
5. 机器人
6. 低空经济
7. 跨境电商
8. 医药健康
9. 消费零售
10. 物流供应链
11. 旅游
12. 网络安全

首版不包含招聘、搜索指数、国家统计局细分指标和商业数据 API。ETF/指数仅作为资本市场预期的代理指标，不代表行业真实市场规模。

## 2. 技术方案

- Python 3.10+
- pandas：清洗、长表、标准化和评分
- requests：RSS 与公开政策网页请求
- feedparser：RSS/Atom 解析
- BeautifulSoup：政策网页标题解析
- yfinance：ETF/指数代理行情
- matplotlib：排名柱状图
- pytest：核心逻辑与离线端到端测试

所有路径通过项目根目录解析，脚本可从任意当前目录启动，不依赖机器绝对路径。

## 3. 项目结构

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
├── requirements.txt
└── README.md
```

采集器互不调用。每个采集器只读取配置并写入自己的原始 CSV；后续统一处理、评分和报告由独立脚本完成。

## 4. 配置模型

`config/industries.json` 中每个行业包含：

```json
{
  "name": "人工智能",
  "keywords": ["人工智能", "AI", "大模型", "AI Agent", "算力"],
  "market_proxy": {
    "ticker": "159819.SZ",
    "name": "人工智能ETF"
  }
}
```

没有合理代理标的时，`market_proxy` 为 `null`。系统为该行业写入 `missing_config` 状态，不抛错、不阻断其他行业。

`config/sources.json` 分别配置新闻 RSS、政策 RSS 或公开列表页。每个来源包含名称、URL、类型和可选解析规则。首版只支持结构稳定且无需登录的公开来源。

## 5. 数据采集

### 5.1 新闻采集器

`fetch_news.py` 请求已配置 RSS/Atom，提取标题、发布日期、链接和来源。按行业关键词进行不区分英文大小写的标题匹配，同一标题对同一行业只计一次。

输出 `data/raw/news_daily.csv`，保留匹配明细，并汇总为行业每日标题数量。请求或解析失败时记录日志；若全部在线来源失败且启用了离线模式，则读取样例数据。

### 5.2 政策采集器

`fetch_policy.py` 独立请求政府部门 RSS 或公开列表页，提取标题、发布日期、链接和来源，再按关键词匹配行业。

输出 `data/raw/policy_daily.csv`。单个页面结构变化只影响该来源，状态记为 `source_error`；其他来源继续运行。

### 5.3 市场采集器

`fetch_market.py` 使用 yfinance 获取配置中代理标的最近约 3 个月的日收盘价，计算 63 个交易日内可获得区间的收益率：

```text
market_return = latest_adjusted_close / first_adjusted_close - 1
```

输出 `data/raw/market_daily.csv`。代理为空时写入 `missing_config`；下载失败时写入 `source_error`；样本不足时写入 `insufficient_data`。这些状态均不终止流程。

## 6. 统一长表

`build_dataset.py` 将三个采集器的汇总结果转换并合并到：

`data/processed/industry_metrics_long.csv`

固定字段：

| 字段 | 含义 |
| --- | --- |
| `industry` | 行业名称 |
| `date` | 指标日期，ISO 8601 |
| `metric` | `news_heat`、`policy_heat` 或 `market_return_3m` |
| `value` | 数值；缺失时为空 |
| `source` | 来源名称或代理标的 |
| `status` | 数据状态 |

允许的首版状态：

- `ok`：在线数据成功
- `sample`：来自离线样例
- `missing_config`：行业未配置市场代理
- `source_error`：来源请求或解析失败
- `insufficient_data`：行情区间不足
- `no_match`：来源成功但当日没有关键词匹配

## 7. 评分模型

`score_industries.py` 对评分日的三个指标分别进行截面百分位评分，映射到 0 至 100：

```text
综合分 = 新闻热度分 × 40% + 市场表现分 × 30% + 政策热度分 × 30%
```

规则：

1. `ok`、`sample` 和 `no_match` 的值可参与评分，其中 `no_match` 的热度值为 0。
2. `missing_config`、`source_error` 和 `insufficient_data` 视为缺失，不用 0 替代。
3. 某行业缺少一个或多个维度时，仅在可用维度上按原权重比例重新归一化。
4. 缺失全部维度时综合分为空，并排在有分行业之后。
5. 输出同时包含原始值、分项分、综合分、可用权重、缺失维度和数据状态，避免把不完整数据伪装成完整结论。

输出 `reports/industry_score.csv`。

## 8. 报告与图表

`generate_report.py` 输出：

- `reports/industry_report.md`
- `charts/industry_score_bar.png`

Markdown 报告包括：

1. 生成日期和数据日期
2. 行业完整排名
3. Top 5 行业及其分项依据
4. 缺失数据与降级运行说明
5. ETF/指数代理指标免责声明
6. 方法说明和风险提示

图表只绘制有综合分的行业，并在标题或注释中说明评分包含代理市场指标。

## 9. 离线与降级策略

项目提供新闻、政策和市场三类样例 CSV。运行入口接受 `--offline` 参数：

- 离线模式不发起网络请求，三个采集器直接复制或规范化样例数据，并标记 `sample`。
- 在线模式中单个来源失败不会中断；失败写入 `logs/error.log`。
- 在线数据完全不可用时，是否回退样例由 `--fallback-samples` 显式控制，默认开启，以保证首次运行可生成完整演示报告。
- 报告必须列出哪些维度或行业使用了样例、缺失配置或发生来源错误。

## 10. 运行入口

- Windows：`./run_all.ps1`
- Linux/macOS：`./run_all.sh`
- Python：`python scripts/run_pipeline.py`

入口按顺序运行三个采集器、长表构建、评分和报告生成。某个采集器返回降级状态时继续后续步骤；只有配置文件损坏、输出目录不可写或核心处理代码异常才返回非零退出码。

## 11. 日志与异常处理

所有脚本使用统一日志配置，同时输出到控制台和 `logs/industry_tracker.log`。异常记录时间、脚本、数据源、行业或 ticker、错误类型和简短原因。

网络请求设置超时和有限重试。日志不得记录访问令牌；首版也不使用任何需要登录或密钥的数据源。

## 12. 测试与验收

测试覆盖：

- 关键词匹配去重和英文大小写
- 空 `market_proxy` 生成缺失状态
- 三类原始数据转换为固定长表字段
- 百分位评分、权重重归一化和全缺失行业
- 报告中的代理指标免责声明和缺失状态
- `--offline` 完整流水线生成三个目标产物

验收条件：

1. 无网络环境执行离线入口成功。
2. 生成的长表字段严格符合设计。
3. 生成 `industry_score.csv`、Markdown 报告和柱状图。
4. 任一采集来源失败不会中断其余流程。
5. 空市场代理不会触发异常。
6. 报告明确说明市场数据是代理指标，并披露样例与缺失状态。

## 13. 后续扩展

首版稳定后，可通过新增采集器和指标配置扩展国家统计局、海关进出口、世界银行、OECD、搜索趋势、招聘报告和政策文本语义分析。扩展指标仍写入同一长表，并在评分配置中显式声明权重，不修改现有采集器接口。
