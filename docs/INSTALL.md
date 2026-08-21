# Ubuntu 22.04 一键部署手册

本项目 v1.0.0-beta 生产部署不使用 Docker。标准入口只有两个根目录脚本：

```bash
sudo ./install.sh
sudo ./uninstall.sh
```

## 常用命令

```bash
# 全新安装或重复安装
sudo ./install.sh

# 只检查环境，不修改系统
sudo ./install.sh --check

# 日常升级，不覆盖 backend.env，不覆盖 frontend-runtime.json 中已有 Key
sudo ./install.sh --upgrade

# 保留数据库、配置和生产数据，重建 Python/前端运行环境
sudo ./install.sh --reinstall

# 安全卸载，默认保留数据库
sudo ./uninstall.sh
```

首次安装会自动生成数据库密码、`SYSTEM_CONFIG_ENCRYPTION_KEY` 和
`ADMIN_CONFIG_TOKEN`，不再要求安装过程中输入第三方 Key。安装完成后在浏览器
“系统配置”页面填写 DeepSeek 和高德 Web 服务 Key。

每次安装、升级或重装都会在数据库迁移前自动备份到项目的 `backups/` 目录。

兼容旧入口：

```bash
bash scripts/install.sh
bash scripts/deploy.sh
```

其中 `scripts/deploy.sh` 等价于：

```bash
sudo ./install.sh --upgrade
```

## 配置文件

后端私密配置：

```text
/etc/esports-site-selection/backend.env
```

关键字段：

```env
APP_ENV=production
DATABASE_URL=postgresql+psycopg://site_selection:<password>@127.0.0.1:5432/site_selection
AMAP_WEB_SERVICE_KEY=<高德 Web 服务 Key>
AMAP_MOCK=false
SCORING_CONFIG_PATH=app/scoring/default.yaml
ENABLE_TRACE=true
ENABLE_FEEDBACK=true
ENABLE_REFLECTION=true
ENABLE_SIMILAR_CASES=true
ENABLE_DEBUG_API=false
ENABLE_DEBUG_ENDPOINTS=false
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
SYSTEM_CONFIG_ENCRYPTION_KEY=<安装脚本自动生成>
ADMIN_CONFIG_TOKEN=<安装脚本自动生成>
SITE_FEEDBACK_STORE_PATH=/var/lib/esports-site-selection/site_feedback.json
AGENT_TRACE_STORE_PATH=/var/lib/esports-site-selection/agent_traces.json
```

前端公开运行配置：

```text
/etc/esports-site-selection/frontend-runtime.json
```

关键字段：

```json
{
  "apiBaseUrl": "/api",
  "amapJsKey": "高德前端 JS Key",
  "amapSecurityJsCode": "高德 JS 安全密钥，可为空",
  "mapProvider": "amap"
}
```

修改前端 JS Key 后只需要：

```bash
sudo systemctl reload nginx
```

不需要重新 `npm run build`。

## 生产数据路径

生产环境固定使用：

```text
/var/lib/esports-site-selection/site_feedback.json
/var/lib/esports-site-selection/agent_traces.json
```

不要把生产 trace / feedback 写到：

```text
/opt/esports-site-selection/app/data
项目目录/data
```

原因：systemd 启用 `ProtectSystem=strict`，只允许：

```text
ReadWritePaths=/var/lib/esports-site-selection
```

## 浏览器一直转圈 / JS pending 排查

先在服务器执行：

```bash
curl -I http://127.0.0.1/
curl -i http://127.0.0.1/config.json
curl -i http://127.0.0.1/runtime-config.json
curl -s http://127.0.0.1/api/system/health
curl -s http://127.0.0.1/api/system/config-status
```

期望：

```text
/                  200 text/html
/config.json       200 application/json
/runtime-config.json 200 application/json
/api/system/health status=ok warnings=[]
```

检查 JS 资源：

```bash
JS=$(python3 - <<'PY'
import re
html=open('/opt/esports-site-selection/app/ai-ss-lvshu-2026-main/frontend/dist/index.html', encoding='utf-8').read()
m=re.search(r'src="([^"]*assets/[^"]+\.js)"', html)
print(m.group(1) if m else '')
PY
)
curl -I "http://127.0.0.1${JS}"
```

如果 `/config.json` 返回 `index.html`，说明 Nginx location 被 SPA fallback 抢走。  
如果 `/runtime-config.json` 返回 `403`，检查：

```bash
sudo ls -l /etc/esports-site-selection/frontend-runtime.json
sudo chmod 755 /etc/esports-site-selection
sudo chmod 644 /etc/esports-site-selection/frontend-runtime.json
sudo systemctl reload nginx
```

如果公网地图不显示，检查：

```bash
curl -s http://127.0.0.1/api/system/config-status
```

确认：

```json
"amapJsKeyConfigured": true
```

## Nginx 配置要求

安装脚本会生成：

```text
/etc/nginx/sites-available/esports-site-selection
/etc/nginx/sites-enabled/esports-site-selection -> sites-available 软链接
```

安装后不允许残留：

```text
__APP_ROOT__
```

检查：

```bash
grep -R "__APP_ROOT__" /etc/nginx /etc/systemd/system/esports-site-selection.service
```

期望无输出。

## 卸载说明

```bash
sudo ./uninstall.sh
```

默认行为：

- 停止并禁用 systemd 服务；
- 删除 Nginx 配置；
- 删除 `backend/.venv`；
- 删除 `frontend/dist`；
- 保留 `/etc/esports-site-selection`，便于直接重装；
- 默认保留 `/var/lib/esports-site-selection`；
- 默认保留 PostgreSQL 数据库。

因此安全重装只需要：

```bash
sudo ./uninstall.sh
sudo ./install.sh
```

也可以不卸载，直接执行：

```bash
sudo ./install.sh --reinstall
```

清除配置和运行数据、但保留数据库：

```bash
sudo ./uninstall.sh --purge
```

只有执行 `--purge-all` 并明确输入：

```text
DELETE_DATABASE
```

才会删除数据库 `site_selection` 和用户 `site_selection`。

```bash
sudo ./uninstall.sh --purge-all
```

## 数据库迁移兼容

迁移脚本支持以下三种情况直接执行 `alembic upgrade head`：

- 全新空数据库；
- 已有 M1/M1.5 表结构但缺少 `alembic_version` 的旧数据库；
- 已经由 Alembic 管理的数据库。

表、字段和索引已经存在时会安全跳过，不需要手工执行 `alembic stamp`，也不要清空数据库。

安装脚本会在 `alembic upgrade head` 前执行一次严格的历史 revision 兼容检查。目前只允许
把已知旧标识 `0014_backfill_amap_business_hours` 转换为规范标识 `0014_amap_hours`，用于兼容
曾经生成过该旧版本号的环境。兼容检查不会创建业务表、不会自动 `stamp`，也不会猜测或修改
任何未知版本。服务器不应再手工使用 `sed` 修改 migration 文件。

后端锁定依赖支持 Python 3.10–3.13，不支持 Python 3.14。Ubuntu 22.04 默认 Python 3.10
符合要求。

> 产品范围提示：收敛版 MVP 不再把独立爬虫作为普通用户能力。现有爬虫部署说明仅供旧环境
> 维护，在后续清理阶段前暂时保留；新部署无需安装爬虫即可完成高德、人工补充和 AI 报告主流程。

## 收敛版 MVP 部署后验收

主系统完成安装或升级后，先执行不改变业务数据的自动检查：

```bash
cd /opt/esports-site-selection/app/ai-ss-lvshu-2026-main
bash scripts/acceptance-mvp.sh
```

脚本检查后端、Nginx、前端路由、配置脱敏、数据源状态和 Alembic 单一 head。完成真实项目后再执行：

```bash
bash scripts/acceptance-mvp.sh --project-id proj_xxx
```

第二条命令会额外核对项目统计与统一数据集 POI 数量、POI 标识唯一性，以及数据准备度固定四类契约。
它不会重新采集数据或生成 AI 报告。

自动检查通过不等于真实业务验收完成。还必须按 [ACCEPTANCE_AMAP_MANUAL_AI_MVP.md](ACCEPTANCE_AMAP_MANUAL_AI_MVP.md)
在浏览器完成地址确认、高德真实采集、人工核实、有限 AI 提问、报告数字追溯及 HTML/PDF 视觉检查。
# 主系统与独立爬虫

主系统的 `install.sh` 只安装 FastAPI、前端、PostgreSQL 配置和 Nginx，不再安装
`crawl4ai` 或下载 Playwright Chromium。这样日常升级不会重复下载数百 MB 浏览器文件，
也不会因为爬虫环境异常阻塞主系统部署。

主系统部署完成后，如需启用 Step 4 公开网页补充，再单独执行：

```bash
cd /opt/esports-site-selection/app/ai-ss-lvshu-2026-main
sudo bash scripts/crawler/install.sh
```

需要提前下载并上传依赖时，使用离线包：

```bash
sudo bash scripts/crawler/install.sh \
  --bundle /home/ubuntu/data/esports-crawler-offline-ubuntu22.04-amd64.tar.gz
```

完整说明见 [CRAWLER_DEPLOYMENT.md](CRAWLER_DEPLOYMENT.md)。
