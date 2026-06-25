# 电竞馆智能选址系统 M1

面向电竞馆投资与运营人员的候选地址初筛系统。系统支持地址地理编码、周边 POI、物业调查、合规风险、规则评分、报告和历史记录。

> 系统结果仅用于初步筛查，最终以当地文化旅游、行政审批、消防和其他主管部门要求为准。

## 最常用命令

服务器默认项目目录按当前生产/测试约定写为 `/home/ubuntu/data/ai-ss-lvshu-2026-main`。如果你的实际目录是 `/opt/esports-site-selection/app`，把下面第一行替换成对应目录即可。

```bash
cd /home/ubuntu/data/ai-ss-lvshu-2026-main

# 日常更新：deploy.sh 已包含 alembic upgrade head，不需要重复手工执行迁移
git pull && bash scripts/deploy.sh

# 健康检查
bash scripts/health-check.sh

# 查看日志
bash scripts/view-logs.sh

# 高德地址解析测试
bash scripts/check-amap-geocode.sh "北京市" "朝阳区阜通东大街6号"

# 数据库备份
bash scripts/backup-db.sh

# 查看配置状态
curl http://127.0.0.1/api/system/config-status

# 编辑前端公开地图配置，修改后只需 reload nginx
sudo nano /etc/esports-site-selection/frontend-runtime.json
sudo systemctl reload nginx
```

## 推荐部署方式

当前项目推荐 Ubuntu 直接部署：

```text
Ubuntu Server
Nginx
Systemd
PostgreSQL + PostGIS
FastAPI/Uvicorn
React/Vite 静态构建
```

Docker Compose 文件如果存在，仅作为备用或本地调试方案；当前生产/测试环境按 Ubuntu 直接部署维护，不强行改成 Docker Compose。

## 部署和运维命令总览

### 配置文件说明

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `/etc/esports-site-selection/backend.env` | 后端私密配置 | 数据库连接、后端高德 Web 服务 Key、评分配置。该文件不允许浏览器访问。 |
| `/etc/esports-site-selection/frontend-runtime.json` | 前端公开运行配置 | 浏览器需要读取的地图 JS Key、安全密钥和地图 provider。该文件会通过 `/runtime-config.json` 暴露给浏览器。 |

后端私密配置示例：

```env
DATABASE_URL=...
AMAP_WEB_SERVICE_KEY=...
AMAP_MOCK=false
SCORING_CONFIG_PATH=app/scoring/default.yaml
```

前端公开运行配置示例：

```json
{
  "amapJsKey": "高德Web端JS API Key",
  "amapSecurityJsCode": "高德安全密钥，可为空",
  "mapProvider": "amap"
}
```

说明：

- `AMAP_WEB_SERVICE_KEY` 是后端 Web 服务 Key，只能放在 `backend.env`；
- `amapJsKey` 是浏览器端高德 JS API Key，会暴露给浏览器，但页面只脱敏展示；
- 前端地图 Key 不再写入 `frontend/.env.production`，也不再依赖 Vite build 固化；
- 修改 `/etc/esports-site-selection/frontend-runtime.json` 后只需 `sudo systemctl reload nginx`；
- 修改 `/etc/esports-site-selection/backend.env` 后需要 `sudo systemctl restart esports-site-selection`。

常用配置命令：

```bash
# 查看配置状态
curl http://127.0.0.1/api/system/config-status

# 编辑后端私密配置
sudo nano /etc/esports-site-selection/backend.env

# 编辑前端公开地图配置
sudo nano /etc/esports-site-selection/frontend-runtime.json

# 修改后端配置后
sudo systemctl restart esports-site-selection

# 修改前端 runtime 配置后
sudo systemctl reload nginx
```

### 首次安装

从空 Ubuntu 22.04/24.04 服务器开始：

```bash
sudo mkdir -p /home/ubuntu/data
sudo chown -R "$USER":"$USER" /home/ubuntu/data
cd /home/ubuntu/data

git clone ssh://git@ssh.github.com:443/xuebailiang-svg/ai-ss-lvshu-2026.git ai-ss-lvshu-2026-main
cd ai-ss-lvshu-2026-main

cp .env.example .env
# 编辑 .env；后端真实密钥仍以后续 scripts/configure-secrets.sh 写入 /etc/esports-site-selection/backend.env 为准

bash scripts/bootstrap-ubuntu-direct.sh
bash scripts/configure-secrets.sh
bash scripts/deploy.sh
curl --fail --show-error http://127.0.0.1/api/health
```

如果没有配置 GitHub SSH，也可以把 `git clone` 换成 HTTPS 或上传 zip 包；后续更新仍建议使用 Git。

### 日常更新部署

`scripts/deploy.sh` 已包含 `alembic upgrade head`，所以日常更新不要再重复手工执行迁移：

```bash
cd /home/ubuntu/data/ai-ss-lvshu-2026-main
git pull
bash scripts/deploy.sh
curl --fail --show-error http://127.0.0.1/api/health
```

如果你想在更新前确认数据库迁移状态，可以只查看，不要额外执行升级：

```bash
cd /home/ubuntu/data/ai-ss-lvshu-2026-main/backend
../backend/.venv/bin/alembic current || alembic current
```

### M1.5 升级部署

从 M1 升级到 M1.5 时，重点是执行新增迁移：

```text
0002_m15_research_enhancements.py
```

推荐命令：

```bash
cd /home/ubuntu/data/ai-ss-lvshu-2026-main
git pull

cd backend
.venv/bin/alembic current || alembic current
cd ..

# deploy.sh 会安装依赖、构建前端、执行 alembic upgrade head、重启 systemd、reload nginx
bash scripts/deploy.sh

cd backend
.venv/bin/alembic current || alembic current
cd ..

curl --fail --show-error http://127.0.0.1/api/health
```

### 保留数据重新部署

适合日常修复、版本更新、重新安装依赖、重新构建前端、重启服务。

```bash
cd /home/ubuntu/data/ai-ss-lvshu-2026-main
git pull
bash scripts/deploy.sh
sudo systemctl restart esports-site-selection
sudo systemctl reload nginx
curl --fail --show-error http://127.0.0.1/api/health
```

该方式：

- 不会删除数据库；
- 不会清空历史评估；
- 不会删除上传文件；
- 适合日常修复和版本更新。

### 危险：会清空数据库，仅开发测试使用

生产环境禁止执行。执行前必须备份数据库。该操作会删除所有评估记录、POI、竞品补充、物业调查和报告。

下面命令默认全部注释，不能直接整段复制执行。确实要在开发测试库清空时，先手工备份，再逐行取消注释，并按提示输入确认。

```bash
# cd /home/ubuntu/data/ai-ss-lvshu-2026-main
# bash scripts/backup-db.sh
#
# read -rp '确认清空开发测试数据库？请输入 RESET_SITE_SELECTION_DB: ' confirm
# if [ "$confirm" != "RESET_SITE_SELECTION_DB" ]; then
#   echo "取消操作"
#   exit 1
# fi
#
# sudo -u postgres psql -c "DROP DATABASE IF EXISTS site_selection;"
# sudo -u postgres createdb --owner=site_selection site_selection
# sudo -u postgres psql -d site_selection -c "CREATE EXTENSION IF NOT EXISTS postgis;"
# bash scripts/deploy.sh
```

### 数据库备份与恢复

备份：

```bash
cd /home/ubuntu/data/ai-ss-lvshu-2026-main
bash scripts/backup-db.sh
ls -lh backups/
```

备份文件保存到：

```text
backups/site_selection_YYYYMMDD_HHMMSS.sql.gz
```

恢复会覆盖当前库数据，必须谨慎执行。建议先在测试库验证备份可用，再由熟悉 PostgreSQL 的人员执行。

```bash
# 先停止后端，避免恢复期间写入数据
sudo systemctl stop esports-site-selection

# 示例：恢复到空库。执行前确认文件名和数据库名。
# gunzip -c backups/site_selection_YYYYMMDD_HHMMSS.sql.gz | \
#   psql "postgresql://site_selection:密码@127.0.0.1:5432/site_selection"

sudo systemctl start esports-site-selection
bash scripts/health-check.sh
```

### 健康检查

统一脚本：

```bash
cd /home/ubuntu/data/ai-ss-lvshu-2026-main
bash scripts/health-check.sh
```

等价的手工检查：

```bash
curl --fail --show-error http://127.0.0.1/api/health
curl -I http://127.0.0.1/
sudo systemctl status esports-site-selection --no-pager
sudo nginx -t
```

### 日志查看

统一脚本：

```bash
cd /home/ubuntu/data/ai-ss-lvshu-2026-main
bash scripts/view-logs.sh
bash scripts/view-logs.sh backend
bash scripts/view-logs.sh nginx
bash scripts/view-logs.sh backend follow
```

等价的手工命令：

```bash
sudo journalctl -u esports-site-selection -n 200 --no-pager
sudo journalctl -u esports-site-selection -f
sudo tail -n 200 /var/log/nginx/error.log
sudo tail -n 200 /var/log/nginx/access.log
```

### 高德接口检查

```bash
cd /home/ubuntu/data/ai-ss-lvshu-2026-main

sudo -u esports-site-selection bash -c \
  'set -a; source /etc/esports-site-selection/backend.env; set +a; \
   bash scripts/check-amap-geocode.sh "北京市" "朝阳区阜通东大街6号"'

sudo -u esports-site-selection bash -c \
  'set -a; source /etc/esports-site-selection/backend.env; set +a; \
   bash scripts/check-amap-geocode.sh "西安市" "雁塔区小寨西路"'
```

说明：

- `AMAP_WEB_SERVICE_KEY` 是后端 Web 服务 Key；
- `frontend-runtime.json.amapJsKey` 是前端地图 JavaScript Key；
- 两者不能混用；
- 脚本会脱敏 Key，不会打印完整密钥。

### 常见问题排查

#### 页面打不开

```bash
curl -I http://127.0.0.1/
sudo systemctl status nginx --no-pager
sudo nginx -t
sudo tail -n 200 /var/log/nginx/error.log
```

处理建议：确认 Nginx 正常、端口 `80` 未被其他服务占用、安全组已开放 TCP `80`。

#### `/api/health` 不通

```bash
curl --fail --show-error http://127.0.0.1:8000/api/health
curl --fail --show-error http://127.0.0.1/api/health
sudo systemctl status esports-site-selection --no-pager
sudo journalctl -u esports-site-selection -n 200 --no-pager
```

处理建议：先确认后端 `127.0.0.1:8000` 是否可用，再看 Nginx `/api` 反向代理。

#### Nginx 配置错误

```bash
sudo nginx -t
sudo ls -l /etc/nginx/sites-enabled/
sudo tail -n 200 /var/log/nginx/error.log
```

处理建议：修复 `/etc/nginx/sites-available/esports-site-selection` 后执行 `sudo systemctl reload nginx`。

#### systemd 服务启动失败

```bash
sudo systemctl status esports-site-selection --no-pager
sudo journalctl -u esports-site-selection -n 200 --no-pager
```

处理建议：重点看 `DATABASE_URL`、Python 依赖、Alembic 迁移、端口 `8000` 是否占用。

#### Alembic 迁移失败

```bash
cd /home/ubuntu/data/ai-ss-lvshu-2026-main/backend
.venv/bin/alembic current
.venv/bin/alembic heads
.venv/bin/alembic upgrade head
```

处理建议：保留英文错误原文，例如 `relation already exists`、`permission denied`，先备份数据库再处理。

#### PostgreSQL 连接失败

```bash
sudo systemctl status postgresql --no-pager
sudo -u postgres psql -d site_selection -c "SELECT 1;"
sudo journalctl -u esports-site-selection -n 200 --no-pager
```

处理建议：检查 `/etc/esports-site-selection/backend.env` 中 `DATABASE_URL` 的用户名、密码、库名和端口。

#### PostGIS 扩展缺失

```bash
sudo -u postgres psql -d site_selection -c "SELECT PostGIS_Version();"
sudo -u postgres psql -d site_selection -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

处理建议：如果提示扩展不存在，先安装 `postgis` 包：`sudo apt-get install -y postgis`。

#### 高德 `ENGINE_RESPONSE_DATA_ERROR (30001)`

```bash
bash scripts/check-amap-geocode.sh "北京市" "朝阳区阜通东大街6号"
```

处理建议：确认使用 `AMAP_WEB_SERVICE_KEY`，不要使用前端 `frontend-runtime.json.amapJsKey`；检查地址是否完整、`city` 是否传了区县/开发区、Key 类型/权限/IP 白名单/配额是否正确。

#### 前端地图不显示

```bash
curl --fail --show-error http://127.0.0.1/runtime-config.json
curl --fail --show-error http://127.0.0.1/api/system/config-status
sudo nano /etc/esports-site-selection/frontend-runtime.json
sudo systemctl reload nginx
```

处理建议：`frontend-runtime.json` 中的 `amapJsKey` 是公开到浏览器的 JS Key；修改后只需 `sudo systemctl reload nginx`，不需要重新构建前端。

#### Vite chunk size warning

```text
Some chunks are larger than 500 kB after minification.
```

处理建议：这是构建体积警告，不是部署失败。只要 `npm run build` exit code 为 `0`，可以继续部署。

#### `.env` 或后端配置未配置

```bash
sudo test -s /etc/esports-site-selection/backend.env && echo ok
sudo grep -E '^(APP_ENV|AMAP_MOCK|SCORING_CONFIG_PATH)=' /etc/esports-site-selection/backend.env
```

处理建议：运行 `bash scripts/configure-secrets.sh`。不要用 `cat` 打印完整配置，避免泄露数据库密码和 Key。

#### 端口 `80` / `8000` / `5432` 被占用

```bash
sudo ss -ltnp | grep -E '(:80|:8000|:5432)' || echo "相关端口当前未监听"
```

处理建议：`80` 应由 Nginx 监听，`8000` 应由后端监听，`5432` 应由 PostgreSQL 本机监听。异常进程需要先确认用途，不能盲目 kill。

## 默认部署架构

本项目默认直接部署到 Ubuntu，不要求 Docker：

```text
浏览器
  ↓ HTTP 80
Nginx（静态前端 + /api 反向代理）
  ↓ 127.0.0.1:8000
systemd → FastAPI/Uvicorn（Python venv）
  ↓ 127.0.0.1:5432
PostgreSQL + PostGIS
```

Docker 文件仍保留为可选方案，但以下生产部署流程完全不使用 Docker。

## Ubuntu 22.04/24.04 直接部署

部署采用关卡式流程。每一步验证成功后才能继续，出现错误时不要跳过。

### 第 1 步：检查服务器环境

```bash
cat /etc/os-release
uname -m
df -h /
free -h
```

要求：

- Ubuntu 22.04 或 24.04；
- 建议至少 2 核 CPU、4 GB 内存；
- 建议至少 20 GB 磁盘可用空间；
- 可使用 `sudo`；
- 端口 `80` 可供 Nginx 使用。

检查端口：

```bash
sudo ss -ltnp | grep -E '(:80|:8000|:5432)' || echo "相关端口当前未监听"
```

如果端口 `80` 已被其他业务占用，应先确认现有 Nginx/Apache 配置，不能直接覆盖。

### 第 2 步：下载项目

```bash
sudo mkdir -p /opt/esports-site-selection
sudo chown -R "$USER":"$USER" /opt/esports-site-selection

git clone https://github.com/xuebailiang-svg/ai-ss-lvshu-2026.git \
  /opt/esports-site-selection/app
cd /opt/esports-site-selection/app
```

验证：

```bash
test -f README.md
test -f backend/pyproject.toml
test -f frontend/package.json
test -f deploy/nginx-direct.conf
echo "项目文件检查通过"
```

### 第 3 步：检查并安装前置软件

项目提供可重复执行的前置环境脚本：已有组件只检查，缺少组件才安装。

```bash
cd /opt/esports-site-selection/app
chmod +x scripts/*.sh
bash scripts/bootstrap-ubuntu-direct.sh
```

脚本检查或安装：

- Python 3.10+、`venv`、`pip`；
- Node.js 20+ 和 npm；
- Nginx；
- PostgreSQL；
- PostGIS；
- Git、curl、编译工具；
- systemd 应用用户和配置目录。

如果不运行脚本，可先手工检查：

```bash
python3 --version
node --version
npm --version
nginx -v
psql --version
systemctl is-active postgresql
systemctl is-active nginx
```

必须满足：

```text
Python >= 3.10
Node.js >= 20
PostgreSQL = active
Nginx = active
```

如果 NodeSource 下载失败，可以在其他具备 Node.js 20+ 的机器执行：

```bash
cd frontend
npm install
npm run build
```

然后将生成的 `frontend/dist/` 上传到服务器。后端运行时不需要 Node.js；Node.js 只用于构建前端。

### 第 4 步：创建数据库

生成一个只包含十六进制字符的数据库密码：

```bash
DB_PASSWORD="$(openssl rand -hex 24)"
echo "数据库密码已生成，请安全保存。"
```

创建用户和数据库。以下命令适用于第一次部署：

```bash
sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='site_selection'" \
  | grep -q 1 \
  || sudo -u postgres psql -c "CREATE USER site_selection WITH PASSWORD '${DB_PASSWORD}';"

sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='site_selection'" \
  | grep -q 1 \
  || sudo -u postgres createdb --owner=site_selection site_selection

sudo -u postgres psql -d site_selection -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

如果数据库用户已经存在，需要明确更新密码：

```bash
sudo -u postgres psql -c "ALTER USER site_selection WITH PASSWORD '${DB_PASSWORD}';"
```

验证数据库：

```bash
sudo -u postgres psql -d site_selection -c "SELECT version();"
sudo -u postgres psql -d site_selection -c "SELECT PostGIS_Version();"
sudo -u postgres psql -tAc "SELECT datname FROM pg_database WHERE datname='site_selection';"
```

必须能看到数据库名称和 PostGIS 版本后才能继续。

### 第 5 步：创建后端环境配置

```bash
sudo install -d -m 0750 -o root -g esports-site-selection \
  /etc/esports-site-selection

sudo cp deploy/backend.env.example \
  /etc/esports-site-selection/backend.env

sudo nano /etc/esports-site-selection/backend.env
```

填写：

```env
APP_ENV=production
DATABASE_URL=postgresql+psycopg://site_selection:替换为第4步密码@127.0.0.1:5432/site_selection
AMAP_WEB_SERVICE_KEY=替换为高德Web服务Key
AMAP_MOCK=false
SCORING_CONFIG_PATH=app/scoring/default.yaml
```

演示环境没有高德 Key 时可以使用：

```env
AMAP_WEB_SERVICE_KEY=
AMAP_MOCK=true
```

设置权限：

```bash
sudo chown root:esports-site-selection \
  /etc/esports-site-selection/backend.env
sudo chmod 0640 /etc/esports-site-selection/backend.env
```

只检查配置项是否存在，不输出密码和 Key：

```bash
sudo grep -E '^(APP_ENV|DATABASE_URL|AMAP_MOCK|SCORING_CONFIG_PATH)=' \
  /etc/esports-site-selection/backend.env \
  | sed 's#DATABASE_URL=.*#DATABASE_URL=***#'
```

### 第 6 步：创建前端运行时配置

```bash
cd /opt/esports-site-selection/app
sudo cp deploy/frontend-runtime.example.json \
  /etc/esports-site-selection/frontend-runtime.json
sudo nano /etc/esports-site-selection/frontend-runtime.json
```

填写允许公开到浏览器的高德 JavaScript API 配置：

```json
{
  "amapJsKey": "替换为高德JSKey",
  "amapSecurityJsCode": "替换为高德安全密钥，可为空",
  "mapProvider": "amap"
}
```

如果暂时不使用在线地图，可以保持为空。高德 Web 服务 Key 不能写入该文件。修改该文件后只需执行 `sudo systemctl reload nginx`，不需要重新构建前端。

### 第 7 步：执行直接部署

```bash
cd /opt/esports-site-selection/app
bash scripts/deploy.sh
```

脚本按顺序执行：

1. 创建 `backend/.venv`；
2. 安装 Python 后端依赖；
3. 安装前端依赖并生成 `frontend/dist`；
4. 执行 `alembic upgrade head`；
5. 安装并启动 systemd 服务；
6. 安装并检查 Nginx 配置；
7. 调用健康接口验证部署。

任何步骤失败都会立即停止，不会假装部署成功。

### 第 8 步：逐项验证

检查后端：

```bash
sudo systemctl status esports-site-selection --no-pager
sudo journalctl -u esports-site-selection -n 100 --no-pager
curl --fail --show-error http://127.0.0.1:8000/api/health
```

检查 Nginx：

```bash
sudo nginx -t
sudo systemctl status nginx --no-pager
curl --fail --show-error http://127.0.0.1/nginx-health
curl --fail --show-error http://127.0.0.1/api/health
```

健康接口预期返回：

```json
{"status":"ok","service":"esports-site-selection","database":"connected"}
```

浏览器访问：

```text
http://服务器公网IP/
```

### 第 9 步：开放防火墙

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw status
```

云服务器安全组也需要开放 TCP `80`。不要对公网开放 `5432` 和 `8000`：

- `5432` 仅供本机后端连接 PostgreSQL；
- `8000` 仅供本机 Nginx 连接 FastAPI。

## 服务管理

```bash
# 查看状态
sudo systemctl status esports-site-selection nginx postgresql --no-pager

# 重启后端
sudo systemctl restart esports-site-selection

# 重载 Nginx
sudo nginx -t && sudo systemctl reload nginx

# 实时查看后端日志
sudo journalctl -u esports-site-selection -f

# 查看 Nginx 错误日志
sudo tail -f /var/log/nginx/error.log
```

## 更新部署

更新前先备份数据库：

```bash
cd /opt/esports-site-selection/app
bash scripts/backup-db.sh
git status --short
git pull --ff-only
bash scripts/deploy.sh
```

验证：

```bash
curl --fail --show-error http://127.0.0.1/api/health
sudo systemctl status esports-site-selection --no-pager
```

## 数据库备份

```bash
cd /opt/esports-site-selection/app
bash scripts/backup-db.sh
ls -lh backups/
```

备份文件位于：

```text
backups/site_selection_YYYYMMDD_HHMMSS.sql.gz
```

验证备份：

```bash
gzip -t backups/site_selection_YYYYMMDD_HHMMSS.sql.gz
zcat backups/site_selection_YYYYMMDD_HHMMSS.sql.gz | head -n 20
```

生产恢复会修改现有数据库，必须先在独立测试库验证备份，再由数据库管理员执行恢复。

## 常见问题

### `502 Bad Gateway`

```bash
sudo systemctl status esports-site-selection --no-pager
sudo journalctl -u esports-site-selection -n 200 --no-pager
curl http://127.0.0.1:8000/api/health
```

### 后端无法连接数据库

保留关键英文错误，例如：

```text
connection refused
password authentication failed
database "site_selection" does not exist
```

检查：

```bash
sudo systemctl status postgresql --no-pager
sudo -u postgres psql -d site_selection -c "SELECT 1;"
sudo journalctl -u esports-site-selection -n 200 --no-pager
```

重点确认 `/etc/esports-site-selection/backend.env` 中的密码与 PostgreSQL 用户密码一致。

### 前端构建失败

```bash
node --version
npm --version
cd /opt/esports-site-selection/app/frontend
npm install
npm run build
```

Node.js 必须不低于 20。

### 高德接口失败

```bash
sudo -u esports-site-selection bash -c \
  'set -a; source /etc/esports-site-selection/backend.env; set +a; \
   [[ -n "$AMAP_WEB_SERVICE_KEY" ]] && echo configured || echo missing'

sudo journalctl -u esports-site-selection -n 200 --no-pager
```

不要在终端或日志中输出完整 Key。

地理编码专项诊断：

```bash
cd /opt/esports-site-selection/app
sudo -u esports-site-selection bash -c \
  'set -a; source /etc/esports-site-selection/backend.env; set +a; \
   bash scripts/check-amap-geocode.sh "西安市" "雁塔区小寨西路"'

sudo -u esports-site-selection bash -c \
  'set -a; source /etc/esports-site-selection/backend.env; set +a; \
   bash scripts/check-amap-geocode.sh "北京市" "朝阳区阜通东大街6号"'
```

Docker Compose 环境可在后端容器内执行：

```bash
docker compose exec backend bash scripts/check-amap-geocode.sh "西安市" "雁塔区小寨西路"
```

脚本会打印 `status`、`info`、`infocode`、`count` 和简要 `geocodes`，但不会输出完整 `AMAP_WEB_SERVICE_KEY`。

## 配置文件位置

| 文件 | 用途 |
| --- | --- |
| `/etc/esports-site-selection/backend.env` | 后端密钥和数据库连接 |
| `/etc/esports-site-selection/frontend-runtime.json` | 前端公开运行配置，通过 `/runtime-config.json` 暴露给浏览器 |
| `/etc/systemd/system/esports-site-selection.service` | 后端 systemd 服务 |
| `/etc/nginx/sites-available/esports-site-selection` | Nginx 配置 |
| `frontend/dist/` | 前端静态文件 |
| `backend/.venv/` | Python 虚拟环境 |

## 本地开发

后端：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
pytest -q
uvicorn app.main:app --reload --port 8000
```

前端：

```bash
cd frontend
npm install
npm test
npm run dev
```

## 更多文档

- [产品说明](docs/PRODUCT.md)
- [系统架构](docs/ARCHITECTURE.md)
- [数据模型](docs/DATA_MODEL.md)
- [评分模型](docs/SCORING_MODEL.md)
- [部署说明](docs/DEPLOYMENT.md)
- [API](docs/API.md)
- [路线图](docs/ROADMAP.md)
- [决策记录](docs/DECISIONS.md)
## Ubuntu 直接部署补充说明

本项目 M1 推荐在 Ubuntu 22.04/24.04 上直接部署，不依赖 Docker。干净服务器按下面顺序执行：

```bash
cd /opt/esports-site-selection/app
bash scripts/bootstrap-ubuntu-direct.sh
bash scripts/configure-secrets.sh
bash scripts/deploy.sh
```

`scripts/configure-secrets.sh` 会安全写入：

- `/etc/esports-site-selection/backend.env`：后端数据库连接、高德 Web 服务 Key、调试开关；
- `/etc/esports-site-selection/frontend-runtime.json`：允许公开到浏览器的高德 JavaScript API Key 和安全密钥。

不要把 `AMAP_WEB_SERVICE_KEY` 写成 `AMAP_API_KEY`；后端只读取 `AMAP_WEB_SERVICE_KEY`。不要把高德 Web 服务 Key 写入 `frontend-runtime.json`。

如果刚刚把当前 SSH 用户加入了 `esports-site-selection` 组，当前会话可能还未生效。可以重新登录，或执行：

```bash
sg esports-site-selection -c 'cd /opt/esports-site-selection/app && bash scripts/deploy.sh'
```

修改前端地图运行时配置后不需要重新构建，只需要 reload Nginx：

```bash
sudo nano /etc/esports-site-selection/frontend-runtime.json
sudo systemctl reload nginx
```

M1 当前报告为规则评分报告，不调用大模型。系统不会读取 `OPENAI_API_KEY`、`DEEPSEEK_API_KEY`、`LLM_API_KEY`、`LLM_BASE_URL` 或 `LLM_MODEL`，也不会调用 OpenAI、DeepSeek、通义千问等 LLM API。

常见错误：

- `Multiple top-level packages discovered in a flat-layout: ['app', 'migrations']`：已通过 `backend/pyproject.toml` 的 `[tool.setuptools] packages = ["app"]` 修复。
- `Property 'env' does not exist on type 'ImportMeta'`：已通过 `frontend/src/vite-env.d.ts` 修复。
- `Expected 1 arguments, but got 0`：已通过 `useRef<any>(null)` 修复。
- `502`：部署脚本会等待 `http://127.0.0.1:8000/api/health` ready 后再检查 Nginx 反向代理。
- `backend.env 不存在或为空`：现在会区分文件不存在、空文件和权限不足。

验收命令：

```bash
cd /opt/esports-site-selection/app
bash scripts/bootstrap-ubuntu-direct.sh
bash scripts/deploy.sh
curl --fail --show-error http://127.0.0.1:8000/api/health
curl --fail --show-error http://127.0.0.1/nginx-health
curl --fail --show-error http://127.0.0.1/api/health
curl -I http://127.0.0.1/
```

## M1.5 真实调研增强版

M1.5 在已通过测试的 M1 基础流程上增量增加真实调研能力，不接消费热力图、Scrapling 爬虫、大模型报告或机器学习。

新增能力：

- 竞品人工补充：在 POI 列表中对“竞品”打开调研表，填写机器数量、面积、硬件、价格、上座率、调查方式、数据来源、可信度和人工核实状态。高德 POI 数据与人工调研数据分层保存。
- 物业调查表：支持建筑面积、实际使用面积、租金、供电、网络、消防、夜间出入口、停车、门头、整改事项、联系人、调查时间、来源和可信度。
- 租金换算：支持月租金或元/㎡/天输入，系统换算月总租金、元/㎡/月、元/㎡/天；填写机器数量后计算每台机器分摊月租金。
- 评分增强：增加竞品强度、价格压力、上座率、物业硬性风险、租金压力、供电网络、消防夜间、数据完整度、人工核实比例。
- 报告增强：报告分为结论摘要、硬性风险、综合评分、数据完整度、竞品分析、交通分析、人口代理指标、商业配套、物业成本、待核实事项、数据来源、评分规则说明。
- 地址对比：历史页可勾选 2～5 个评估记录进行表格和简单图表对比。
- 历史增强：支持城市、推荐等级、硬性风险筛选，创建时间/评分/完整度/可信度/更新时间排序，并支持重新评分。

新增/增强 API：

- `PUT /api/evaluations/{id}/property`
- `PUT /api/competitors/{id}/enrichment`
- `GET /api/competitors/{id}/enrichments`
- `POST /api/evaluations/compare`
- `GET /api/health/config`

数据库迁移：

- `backend/migrations/versions/0002_m15_research_enhancements.py`
- 扩展 `property_surveys` 和 `competitor_enrichments`
- 新增 `competitor_survey_records` 保存每次竞品人工调研历史

重要边界：

- M1.5 当前报告仍是规则评分报告，不调用大模型。
- 人口相关内容只显示为 POI 代理指标，不显示为真实人口。
- 上座率等人工判断会在报告中标注为“估算值”。
- 硬性风险与普通评分分离，高分不能覆盖准入风险。
