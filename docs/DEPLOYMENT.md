# 直接部署架构

生产默认直接部署在 Ubuntu：Nginx 监听公网端口并托管 `frontend/dist`，`/api` 反向代理到仅监听 `127.0.0.1:8000` 的 FastAPI；FastAPI 由 systemd 管理，通过本机 `127.0.0.1:5432` 访问 PostgreSQL/PostGIS。

完整命令见项目根目录 `README.md`。核心脚本：

- `scripts/bootstrap-ubuntu-direct.sh`：检查并安装 Python、Node.js、Nginx、PostgreSQL/PostGIS。
- `scripts/deploy.sh`：安装依赖、构建前端、迁移数据库、安装 systemd/Nginx 配置并执行健康检查。
- `scripts/backup-db.sh`：使用本机 `pg_dump` 生成压缩备份。
- `scripts/health-check.sh`：统一检查 systemd、Nginx、后端 API、Nginx 反向代理和首页。
- `scripts/view-logs.sh`：查看后端 journal 和 Nginx access/error 日志。

配置与密钥存储在 `/etc/esports-site-selection/backend.env`，权限必须为 `root:esports-site-selection 0640`。数据库和 Uvicorn 端口不得暴露公网。

Docker Compose 文件仅作为可选部署方式保留，不是默认生产路径。

## 常用运维命令

`scripts/deploy.sh` 已包含 `alembic upgrade head`，日常更新不要重复手工执行迁移。

```bash
cd /home/ubuntu/data/ai-ss-lvshu-2026-main

# 日常更新
git pull && bash scripts/deploy.sh

# 保留数据重新部署
bash scripts/deploy.sh
sudo systemctl restart esports-site-selection
sudo systemctl reload nginx

# 健康检查
bash scripts/health-check.sh

# 查看日志
bash scripts/view-logs.sh
bash scripts/view-logs.sh backend follow

# 数据库备份
bash scripts/backup-db.sh
```

危险操作不要放进 `deploy.sh`。清空数据库仅允许开发测试环境手工确认后执行，生产环境禁止执行。

## Ubuntu 22.04/24.04 直接部署验收流程

默认生产部署方式是 Ubuntu 直接部署，不使用 Docker。推荐顺序：

```bash
cd /opt/esports-site-selection/app
bash scripts/bootstrap-ubuntu-direct.sh
bash scripts/configure-secrets.sh
bash scripts/deploy.sh
```

### 数据库

PostgreSQL/PostGIS 可使用系统包安装。创建项目数据库示例：

```sql
CREATE USER site_selection WITH PASSWORD '替换为强密码';
CREATE DATABASE site_selection OWNER site_selection;
\c site_selection
CREATE EXTENSION IF NOT EXISTS postgis;
```

`DATABASE_URL` 写入 `/etc/esports-site-selection/backend.env`，不要写入前端配置。

### 高德 Key

- 后端：`AMAP_WEB_SERVICE_KEY`，只放在 `/etc/esports-site-selection/backend.env`。
- 前端：`VITE_AMAP_JS_KEY` 和 `VITE_AMAP_SECURITY_JS_CODE`，写入 `frontend/.env.production`，会被打包到浏览器静态资源。

修改任何 `VITE_` 变量后必须重新执行 `bash scripts/deploy.sh` 或 `cd frontend && npm run build`。

### 大模型说明

M1 当前报告为规则评分报告，不调用大模型。当前后端不会读取或调用 `OPENAI_API_KEY`、`DEEPSEEK_API_KEY`、`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`。

### 权限和组

`/etc/esports-site-selection/backend.env` 推荐权限：

```bash
sudo chown root:esports-site-selection /etc/esports-site-selection/backend.env
sudo chmod 0640 /etc/esports-site-selection/backend.env
```

如果刚刚把当前 SSH 用户加入 `esports-site-selection` 组，当前会话可能还未生效。请重新登录，或执行：

```bash
sg esports-site-selection -c 'cd /opt/esports-site-selection/app && bash scripts/deploy.sh'
```

### 常见部署错误

- `Multiple top-level packages discovered in a flat-layout: ['app', 'migrations']`：后端只打包 `app`，不要把 `migrations` 当 Python 包发布。
- `Property 'env' does not exist on type 'ImportMeta'`：需要 `frontend/src/vite-env.d.ts`。
- `Expected 1 arguments, but got 0`：React `useRef` 需要传入初始值，例如 `useRef<any>(null)`。
- `502`：通常是 Nginx 检查太早。`scripts/deploy.sh` 已改为等待后端 `127.0.0.1:8000/api/health` ready 后再检查 Nginx。
- Key 配错：后端必须使用高德 Web 服务 Key，前端 JS Key 不能替代后端 Web 服务 Key。

### 验收命令

```bash
cd /opt/esports-site-selection/app
bash scripts/bootstrap-ubuntu-direct.sh
bash scripts/deploy.sh
curl --fail --show-error http://127.0.0.1:8000/api/health
curl --fail --show-error http://127.0.0.1/nginx-health
curl --fail --show-error http://127.0.0.1/api/health
curl -I http://127.0.0.1/
```
