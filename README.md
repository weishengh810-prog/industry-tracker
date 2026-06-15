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

`scripts/run_pipeline.py` 统计有效归档日期与当前数据日期的并集，并把
`history_days` 传给评分器；当天已归档时通过集合去重，不会重复计数：

- `history_days < 28`：进入 `试运行评分模式`。每个主指标优先使用有效 `growth_rate_4w`；某行业的该指标增长率不可用时，回退到最新截面值。
- `history_days >= 28`：进入正式 momentum 阶段，只允许使用有效 `growth_rate_4w`，不再回退到最新截面值。

无论处于哪个阶段，每个指标独立计算行业截面百分位，再汇总到资本动量和技术活跃度，市场收益率、论文数、GitHub 仓库数等不同量纲的原始值不会直接相加。任一底层指标至少需要 3 个可用行业才能形成百分位。

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

- `试运行评分模式`：历史不足 28 天，临时评分仅供观察
- `完整 momentum 模式`
- `部分 momentum 模式`：正式阶段个别指标缺失时，仅用有效增长率并按可用维度重新归一化
- `历史数据不足，暂不排名`

## 输出

```text
data/raw/*.csv
data/processed/industry_metrics_long.csv
data/processed/momentum_features.csv
reports/industry_score.csv
reports/industry_report.md
charts/industry_score_bar.png
docs/index.html
docs/data/meta.json
docs/data/ranking.json
docs/data/history.csv
logs/industry_tracker.log
logs/error.log
```

## Web 部署

项目同时保留两种 Web 运行方式：

| 版本 | 部署位置 | 数据读取方式 | 适用场景 |
| --- | --- | --- | --- |
| FastAPI 动态版 | ECS，配合现有 systemd 与 Nginx 配置 | 读取 `web/industry.db`，提供 `/api/...` 动态 API | 服务器端查询、筛选和动态 CSV 下载 |
| GitHub Pages 静态版 | 当前 Git 分支的 `/docs` 目录 | 读取已提交的 `docs/data/*.json` 和 `docs/data/history.csv` | 无服务器公开展示 |

静态版不会请求 FastAPI，也不会替代或删除 ECS 上的动态服务。

### 手动导出静态站点数据

先把当前 pipeline 产物写入 SQLite，再生成 GitHub Pages 数据：

```bash
python scripts/store_to_db.py
python scripts/export_static.py
```

导出器直接读取本地 SQLite，不要求 FastAPI 或 Uvicorn 正在运行。需要本地预览时，应通过 HTTP 服务访问，避免浏览器对 `file://` 下 `fetch` 的限制：

```bash
python -m http.server 8000 --directory docs
```

然后访问 `http://localhost:8000/`。

### 开启 GitHub Pages

1. 打开 GitHub 仓库的 `Settings`。
2. 进入 `Pages`。
3. Source 选择从分支部署。
4. Branch 选择当前发布分支。
5. Folder 选择 `/docs`，保存设置。

仓库名为 `industry-tracker` 时，页面地址通常为：
`https://weishengh810-prog.github.io/industry-tracker/`。

### 接入每日 cron

现有 `scripts/daily_update.sh` 保留 pipeline、归档和报告提交逻辑，并在 pipeline 完成后依次执行：

```bash
python scripts/run_pipeline.py
python scripts/store_to_db.py
python scripts/export_static.py
git add docs/ reports/ charts/ data/ archives/
git commit
git push
```

脚本使用运行锁避免重复并发执行，并把输出追加到 `logs/daily_update.log`。只有 `git diff --cached --quiet` 检测到 staged changes 时才会 commit 和 push；push 失败会记录错误并以非零状态退出。提交推送到 GitHub 后，GitHub Pages 会自动从发布分支的 `/docs` 目录更新静态页面。

ECS 每天通过 cron 调用脚本，推荐配置：

```cron
0 6 * * * /home/admin/industry-tracker/scripts/daily_update.sh >> /home/admin/industry-tracker/logs/daily_update.log 2>&1
```

ECS 如需自动 push，应在服务器外部安全配置 SSH deploy key、Git credential helper 或等价凭证。不要把 SSH 私钥、token、密码、服务器地址或其他凭证写入仓库，也不要放入 GitHub Pages 会公开发布的 `docs/` 目录。

服务器侧可用以下命令验证完整链路：

```bash
cd /home/admin/industry-tracker
bash scripts/daily_update.sh
tail -n 100 logs/daily_update.log
git status
```

提交前可运行静态发布自检，检查数据完整性、动态 API 隔离和常见敏感凭证特征：

```bash
python scripts/check_static_publish.py
```

## 测试

```bash
python scripts/fetch_market.py --offline
python scripts/run_pipeline.py --offline
python -m pytest -v
```

本系统比较的是行业相对自身历史的加速程度，不是行业绝对规模。小行业若快速升温可能排名靠前；大行业若增速放缓排名会下降。离线样例只用于验证流程，不能作为投资、政策或经营决策依据。
