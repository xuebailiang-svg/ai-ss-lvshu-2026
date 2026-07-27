# 爬虫数据补充模块

本模块用于把公开网页中的经营线索补充到现有统一数据模型。

## 合规边界

- 只抓取允许访问的公开页面。
- 不绕过登录、验证码、反爬、付费墙或访问控制。
- 不把爬虫结果直接当作真实调研结论。
- 爬虫结果默认作为线索保存，必须人工确认后才能作为正式事实参与后续分析。

## 配置

默认关闭爬虫执行，但搜索发现默认可配置开启：

```env
CRAWLER_ENABLED=false
CRAWLER_PROVIDER=crawl4ai
CRAWLER_TIMEOUT_SECONDS=60
CRAWLER_MAX_PAGES_PER_TASK=5
CRAWLER_MAX_TASKS_PER_PROJECT=50
CRAWLER_RATE_LIMIT_SECONDS=5
CRAWLER_ALLOWED_DOMAINS=
CRAWLER_BLOCKED_DOMAINS=
CRAWLER_SEARCH_ENABLED=true
CRAWLER_SEARCH_PROVIDER=duckduckgo_html
CRAWLER_SEARCH_MAX_RESULTS=5
CRAWLER_SEARCH_TIMEOUT_SECONDS=10
CRAWLER_SEARCH_ALLOWED_DOMAINS=
```

## 数据流

```text
高德 POI / 人工上传候选对象
  -> 已有 source_url 则直接抓取
  -> 没有 source_url 则按名称、地址、项目位置搜索公开网页
  -> crawl4ai 转 Markdown
  -> 字段抽取
  -> 写入 raw_data.crawler_detail
  -> status=pending_review
  -> 人工确认
```

## 第一版限制

- 搜索发现使用公开搜索结果页，不保证每个站点都能访问。
- 大众点评、美团、贝壳等站点如果限制访问，只记录失败原因，不做绕过。
- 租金搜索只生成待确认线索，不计算市场均价、不判断盈利能力。
