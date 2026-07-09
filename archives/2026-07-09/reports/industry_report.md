# 行业发展动量报告

- 生成时间：2026-07-09 08:05:49 CST
- 数据日期：2026-07-09
- 当前评分模式：历史数据不足，暂不排名
- 模式说明：正式评分仅使用有效 `growth_rate_4w`。
- 未进入主评分的指标：market_return_3m;market_return_4w;arxiv_paper_count_4w;github_repo_count_4w

## 行业排名

当前暂无可排名行业。离线样例或新部署通常需要积累约 56 天历史后，才能计算第一批 `growth_rate_4w`。

## Top 5

- 当前暂无可排名行业。

## 辅助观察：成交量

`market_volume_change_4w` 仅作辅助观察，不进入主评分。

| 行业 | 当期值 | 4周增长率 | 历史状态 |
| --- | --- | --- | --- |
| 人工智能 | 0.17 | - | insufficient_history |
| 低空经济 | 0.14 | - | insufficient_history |
| 储能 | -0.50 | - | insufficient_history |
| 医药健康 | 3.48 | - | insufficient_history |
| 半导体 | 0.08 | - | insufficient_history |
| 新能源汽车 | -0.23 | - | insufficient_history |
| 旅游 | -0.48 | - | insufficient_history |
| 机器人 | -0.35 | - | insufficient_history |
| 消费零售 | -0.09 | - | insufficient_history |
| 网络安全 | -0.22 | - | insufficient_history |
| 跨境电商 | -0.11 | - | insufficient_history |

物流供应链使用 SHPP 作为全球市场代理。该 ETF 可能流动性偏低，成交量变化需要结合 `insufficient_data` 状态谨慎解释。

## 网络安全专项信号

`nvd_cve_count_4w` 第一版只覆盖网络安全，不能单独进行行业横向评分，因此暂不进入 `external_signal` 主评分。

| 行业 | 近4周新增 CVE | 4周增长率 | 历史状态 |
| --- | --- | --- | --- |
| 网络安全 | 6631.00 | - | insufficient_history |

## 方法说明

- 正式评分只使用有效 `growth_rate_4w`，不回退到当期绝对值。
- 任一底层指标至少 3 个行业的 `momentum_status=ok` 才能进入截面百分位。
- `capital_momentum` 权重 35%，由 `market_return_3m` 和 `market_return_4w` 构成。
- `tech_activity` 权重 65%，由 `arxiv_paper_count_4w` 和 `github_repo_count_4w` 构成。
- 某个指标历史不足只排除该指标；可用维度按原始权重重新归一化。
- `external_signal` 字段已预留，待多个行业拥有可比专项指标后再启用。

本系统比较的是行业相对自身历史的加速程度，不是行业绝对规模。
小行业若快速升温可能排名靠前；大行业若增速放缓排名会下降。
ETF 为全球市场代理，不代表中国行业真实基本面。
当前评分模式：历史数据不足，暂不排名

数据来源：公开 ETF 行情、arXiv 学术论文、GitHub 开源仓库、NVD 漏洞数据库。

## 数据状态

`sample` 表示离线样例；`missing_config` 表示该来源不覆盖该行业；`source_error` 表示请求或解析失败；`insufficient_data` 表示当期样本不足；`insufficient_history` 只用于历史特征，表示尚不能计算增长率。
