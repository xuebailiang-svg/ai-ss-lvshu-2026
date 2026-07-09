# Ubuntu 22.04 一键部署手册

本项目 v1.0-beta 生产部署不使用 Docker。标准入口只有两个根目录脚本：

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

# 安全卸载，默认保留数据库
sudo ./uninstall.sh
```

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
- 删除 `/etc/esports-site-selection`；
- 默认保留 `/var/lib/esports-site-selection`；
- 默认保留 PostgreSQL 数据库。

只有明确输入：

```text
DELETE_DATABASE
```

才会删除数据库 `site_selection` 和用户 `site_selection`。
