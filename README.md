# 行业发展动量监测系统

这是一个使用免费、无需登录的公开数据源构建的 Python 行业动量跟踪器。系统覆盖 12 个行业，生成统一长表、逐指标历史特征、行业相对动量排名、Markdown 报告和图表。

## 数据源

- 市场代理：Yahoo Finance 上的美股 ETF，下载至少 120 个自然日行情。
- 技术活跃度：arXiv API 与 GitHub Search API。
- 网络安全专项信号：NVD CVE API。
- 新闻：公开 RSS，仅保留在长表中，不参与主评分。
- 政策：采集器保留；当前无合规在线源时输出 `missing_config`，不参与主评分。

项目不使用指定的国内政府域名或 A 股 ETF。ETF 只是全球市场代理，不代表中国行业真实基本面。

## 运行

安装 Python 3.10+ 后执行：

```bash
python -m pip install -r requirements.txt
python scripts/run_pipeline.py --offline
```

在线运行：

```bash
python scripts/run_pipeline.py
```

禁用新闻等旧采集器的样例回退：

```bash
python scripts/run_pipeline.py --no-fallback-samples
```

GitHub 未认证 API 按每次请求后 60–75 秒节流；arXiv 至少 3 秒；NVD 至少 6 秒。三个来源均使用 `data/cache/<source>_YYYY-MM-DD.json` 当日缓存。

## 流水线

```text
news_daily.csv
policy_daily.csv
market_daily.csv
arxiv_daily.csv
github_daily.csv
nvd_daily.csv
        |
        v
industry_metrics_long.csv
        |
        v
momentum_features.csv
        |
        v
industry_score.csv -> industry_report.md + industry_score_bar.png
```

采集器统一通过 `_run_collector` 执行。任一采集器崩溃时写入 `source_error` 行，后续采集器、数据构建、评分和报告继续运行。

## 长表契约

所有 daily CSV 与合并长表固定使用：

```text
industry,date,metric,value,source,status
```

daily 状态白名单：

- `ok`
- `sample`
- `no_match`
- `missing_config`
- `source_error`
- `insufficient_data`

`insufficient_history` 只出现在 `momentum_features.csv`，不会写入 daily CSV。

市场指标：

- `market_return_3m`
- `market_return_4w`
- `market_volume_change_4w`

技术与专项指标：

- `arxiv_paper_count_4w`
- `github_repo_count_4w`
- `nvd_cve_count_4w`

## 历史特征

`scripts/build_momentum_features.py` 按 `industry + metric` 独立判断历史是否充足：

- `growth_rate_4w = 近 4 周均值 / 前 4 周均值 - 1`
- `z_score_12w = (当期值 - 近 12 周均值) / 近 12 周标准差`
- `freshness_days = 构建日期 - 最新数据日期`

增长率通常需要约 56 天覆盖。前 4 周均值为 0、最新值不可用或历史不足时，状态为 `insufficient_history`。某个指标历史不足不会让其他指标或整个系统一起回退。

## 评分

评分只使用 `growth_rate_4w`，不回退到当期绝对值。任一底层指标至少需要 3 个行业的 `momentum_status=ok` 才能进入截面百分位。

```text
capital_momentum 35%
  - market_return_3m
  - market_return_4w

tech_activity 65%
  - arxiv_paper_count_4w
  - github_repo_count_4w
```

同一维度内取可用底层指标百分位的均值。行业缺少某个维度时，按 35:65 的原始权重在可用维度上重新归一化。

`market_volume_change_4w` 和 `nvd_cve_count_4w` 只进入报告辅助观察区。NVD 第一版仅覆盖网络安全，不能进行行业横向比较，因此 `external_signal_score` 暂为空。

评分模式：

- `完整 momentum 模式`
- `部分 momentum 模式`
- `历史数据不足，暂不排名`

## 输出

```text
data/raw/*.csv
data/processed/industry_metrics_long.csv
data/processed/momentum_features.csv
reports/industry_score.csv
reports/industry_report.md
charts/industry_score_bar.png
logs/industry_tracker.log
logs/error.log
```

## 测试

```bash
python scripts/fetch_market.py --offline
python scripts/run_pipeline.py --offline
python -m pytest -v
```

本系统比较的是行业相对自身历史的加速程度，不是行业绝对规模。小行业若快速升温可能排名靠前；大行业若增速放缓排名会下降。离线样例只用于验证流程，不能作为投资、政策或经营决策依据。
