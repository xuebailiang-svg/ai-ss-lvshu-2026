# 爬虫数据补充模块

本模块用于把公开网页中的经营线索补充到现有统一数据模型中。

## 合规边界

- 只抓取允许访问的公开页面。
- 不绕过登录、验证码、反爬、付费墙或访问控制。
- 不保存完整页面作为业务事实，只保存结构化抽取结果、来源链接和任务状态。
- 爬虫结果默认 `pending_review`，必须人工确认后才能作为正式事实参与后续分析。

## 配置

默认关闭：

```env
CRAWLER_ENABLED=false
CRAWLER_PROVIDER=crawl4ai
CRAWLER_TIMEOUT_SECONDS=60
CRAWLER_MAX_PAGES_PER_TASK=5
CRAWLER_MAX_TASKS_PER_PROJECT=50
CRAWLER_RATE_LIMIT_SECONDS=5
CRAWLER_ALLOWED_DOMAINS=
CRAWLER_BLOCKED_DOMAINS=
```

## 数据流

```text
高德 POI / 人工上传候选对象
  -> 公开 URL 抓取
  -> crawl4ai 转 Markdown
  -> 字段抽取
  -> 写入 raw_data.crawler_detail
  -> status=pending_review
  -> 人工确认
```

## 第一版限制

- 不做搜索引擎自动检索；只处理候选对象已有 `source_url`、`detail_url`、`shop_url` 等公开链接。
- 无公开链接时任务会记录为 `skipped`。
- 美团、大众点评、贝壳等站点如限制访问，只记录失败原因，不做绕过。
