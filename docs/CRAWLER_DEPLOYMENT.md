# 独立爬虫部署说明

## 为什么单独部署

主系统和爬虫使用同一套业务代码与 PostgreSQL 数据库，但运行环境分离：

```text
FastAPI 主服务
  └─ 创建 crawl_tasks（pending），立即返回

独立 crawler Worker
  └─ 读取 pending 任务
     └─ 搜索公开网页
        └─ crawl4ai + Chromium 抓取
           └─ 保存为 pending_review，等待人工确认
```

这样主系统升级、启动和健康检查不再下载 Chromium，也不会因为单次抓取耗时而产生 `504 Gateway Timeout`。

爬虫仍遵守以下边界：

- 只访问允许公开访问的网页。
- 不绕过登录、验证码、付费墙或反爬限制。
- 抓取数据默认 `pending_review`。
- 不覆盖人工确认字段。
- 未经人工确认的数据不作为正式评分事实。

## 部署顺序

先部署主系统：

```bash
cd /home/ubuntu/data/ai-ss-lvshu-2026-main
sudo ./install.sh --upgrade
```

主系统部署完成后，按以下任一方式单独安装爬虫。

## 方式一：服务器在线安装

```bash
cd /opt/esports-site-selection/app/ai-ss-lvshu-2026-main
sudo bash scripts/crawler/install.sh
```

该命令只在首次安装或爬虫依赖升级时下载 `crawl4ai`、Playwright Chromium 和系统库。后续普通主系统升级不会重新下载浏览器。

## 方式二：提前下载并上传离线包

离线包必须在与生产服务器相同的 `Ubuntu 22.04 amd64` 环境构建：

```bash
cd ai-ss-lvshu-2026-main
bash scripts/crawler/build-offline-bundle.sh
```

生成：

```text
crawler/esports-crawler-offline-ubuntu22.04-amd64.tar.gz
```

上传项目 ZIP 和该离线包到服务器，例如：

```text
/home/ubuntu/data/ai-ss-lvshu-2026-main.zip
/home/ubuntu/data/esports-crawler-offline-ubuntu22.04-amd64.tar.gz
```

先正常部署主系统，再安装离线爬虫：

```bash
cd /opt/esports-site-selection/app/ai-ss-lvshu-2026-main
sudo bash scripts/crawler/install.sh \
  --bundle /home/ubuntu/data/esports-crawler-offline-ubuntu22.04-amd64.tar.gz
```

离线包包含：

- Python wheelhouse
- 固定版本 `crawl4ai`
- 与 Playwright 版本匹配的 Chromium
- Ubuntu 22.04 浏览器运行依赖 `.deb`
- 实际解析后的 Python 依赖清单

不要在 Windows 上构建 Linux 离线包。

## 启用与验证

安装 Worker 后，在 Web 配置页打开“启用爬虫”并保存，然后验证：

```bash
sudo systemctl status esports-site-selection-crawler --no-pager -l
curl -s http://127.0.0.1/api/data-sources/crawler/runtime
curl -s -X POST http://127.0.0.1/api/data-sources/crawler_competitor/check
```

正常状态应包含：

```json
{
  "installed": true,
  "reachable": true,
  "status": "ok",
  "browser_ready": true
}
```

查看日志：

```bash
sudo journalctl -u esports-site-selection-crawler -n 200 --no-pager
sudo journalctl -u esports-site-selection-crawler -f
```

## 升级

只改主业务代码时：

```bash
sudo ./install.sh --upgrade
```

主安装脚本会在 Worker 已安装时重启它，但不会重建爬虫虚拟环境或重新下载 Chromium。

只有 `crawler/requirements.txt` 或浏览器运行时版本发生变化时，才重新执行：

```bash
sudo bash scripts/crawler/install.sh
```

或使用新离线包：

```bash
sudo bash scripts/crawler/install.sh --bundle /path/new-crawler-bundle.tar.gz
```

## 卸载

只卸载爬虫，保留浏览器缓存：

```bash
sudo bash scripts/crawler/uninstall.sh
```

彻底删除爬虫虚拟环境、浏览器缓存和健康状态：

```bash
sudo bash scripts/crawler/uninstall.sh --purge
```

卸载爬虫不会删除项目、`crawl_tasks`、竞品、配套或租金数据，也不会影响主系统。

## 常见问题

### 配置页显示“尚未安装”

```bash
sudo systemctl status esports-site-selection-crawler --no-pager -l
sudo cat /var/lib/esports-site-selection/crawler/worker-health.json
```

### Worker 已启动但配置页显示“已禁用”

在配置页启用爬虫，或确认 `/etc/esports-site-selection/backend.env` 中：

```env
CRAWLER_ENABLED=true
```

数据库配置优先于 `.env`，如果曾在配置页保存过关闭状态，应在配置页重新打开并保存。

### 离线 `.deb` 安装失败

保留英文错误原文，例如：

```text
dependency problems - leaving unconfigured
```

应在相同版本的 Ubuntu 22.04 amd64 环境重新生成离线包。不要用其他 Ubuntu 版本或 Windows 生成的依赖包混装。
