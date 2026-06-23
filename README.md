# 电竞馆智能选址系统 M1

面向电竞馆投资与运营人员的候选地址初筛系统。系统支持地址地理编码、周边 POI、物业调查、合规风险、规则评分、报告和历史记录。

> 系统结果仅用于初步筛查，最终以当地文化旅游、行政审批、消防和其他主管部门要求为准。

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

### 第 6 步：创建前端构建配置

```bash
cd /opt/esports-site-selection/app
cp deploy/frontend.env.example frontend/.env.production
nano frontend/.env.production
```

填写允许公开到浏览器的高德 JavaScript API 配置：

```env
VITE_AMAP_JS_KEY=替换为高德JSKey
VITE_AMAP_SECURITY_JS_CODE=替换为高德安全密钥
```

如果暂时不使用在线地图，可以保持为空。高德 Web 服务 Key 不能写入该文件。

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
| `/etc/systemd/system/esports-site-selection.service` | 后端 systemd 服务 |
| `/etc/nginx/sites-available/esports-site-selection` | Nginx 配置 |
| `frontend/.env.production` | 前端公开构建参数 |
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
