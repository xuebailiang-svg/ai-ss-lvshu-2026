# 电竞馆智能选址系统 M1

面向电竞馆投资与运营人员的候选地址初筛系统。M1 支持地址地理编码、周边 POI、物业调查、合规风险、规则评分、报告和历史记录。

> 系统结果仅用于初步筛查，最终以当地文化旅游、行政审批、消防和其他主管部门要求为准。

## 服务组成

| 服务 | 容器 | 用途 | 是否暴露到公网 |
| --- | --- | --- | --- |
| Web | `web` | Nginx、React 静态文件、API 反向代理 | 是，默认 `80` |
| Backend | `backend` | FastAPI、Alembic 数据库迁移 | 否 |
| Database | `db` | PostgreSQL 16 + PostGIS 3.4 | 否 |

## Ubuntu 服务器部署

以下命令适用于 Ubuntu 22.04/24.04。建议至少准备 2 核 CPU、4 GB 内存和 20 GB 可用磁盘空间。

### 1. 安装基础工具

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git openssl
```

### 2. 安装 Docker Engine 和 Docker Compose

如果服务器已经安装并能正常执行 `docker compose version`，可以跳过本节。

```bash
# 删除可能冲突的非官方软件包；全新服务器执行不会影响数据
for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
  sudo apt-get remove -y "$pkg" 2>/dev/null || true
done

# 添加 Docker 官方 APT 仓库
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null

sudo apt-get update
sudo apt-get install -y \
  docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo systemctl enable --now docker
sudo docker run --rm hello-world
sudo docker compose version
```

可选：允许当前用户不加 `sudo` 使用 Docker。执行后需要重新登录 SSH，或临时执行 `newgrp docker`。

```bash
sudo usermod -aG docker "$USER"
newgrp docker
docker version
docker compose version
```

> `docker` 用户组等同于较高的服务器权限，只应加入可信用户。

### 3. 下载项目

将 `<仓库地址>` 替换为实际 GitHub 仓库 URL。

```bash
sudo mkdir -p /opt/esports-site-selection
sudo chown -R "$USER":"$USER" /opt/esports-site-selection

git clone <仓库地址> /opt/esports-site-selection/app
cd /opt/esports-site-selection/app
```

如果代码已经上传到服务器，只需要进入包含 `docker-compose.yml` 的目录：

```bash
cd /opt/esports-site-selection/app
```

### 4. 创建生产环境配置

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

至少修改以下配置：

```env
POSTGRES_DB=site_selection
POSTGRES_USER=site_selection
POSTGRES_PASSWORD=替换为强密码
DATABASE_URL=postgresql+psycopg://site_selection:同一个强密码@db:5432/site_selection

# 高德 Web 服务 Key，只发送到后端容器
AMAP_WEB_SERVICE_KEY=替换为高德Web服务Key
AMAP_MOCK=false

# 高德 JavaScript API 的公开端配置
VITE_AMAP_JS_KEY=替换为高德JSKey
VITE_AMAP_SECURITY_JS_CODE=替换为高德安全密钥

APP_ENV=production
APP_BASE_URL=http://服务器公网IP
WEB_PORT=80
```

可用下面的命令生成仅包含字母和数字的数据库密码：

```bash
openssl rand -hex 24
```

注意：

- `POSTGRES_PASSWORD` 和 `DATABASE_URL` 中的密码必须一致。
- 密码若包含 `@`、`:`、`/`、`#` 等字符，必须先进行 URL 编码；不熟悉 URL 编码时可使用上面的十六进制密码。
- `.env` 不可提交到 Git，项目的 `.gitignore` 已忽略该文件。
- 真实部署使用 `AMAP_MOCK=false`。临时演示且没有高德 Key 时可改为 `AMAP_MOCK=true`。
- `VITE_AMAP_*` 在前端镜像构建时写入静态资源，修改后必须重新执行 `docker compose build web`。

### 5. 检查配置

```bash
cd /opt/esports-site-selection/app

# 检查 Compose 文件语法和变量替换；输出可能包含密码，不要粘贴到公开场所
docker compose config --quiet

# 确认只对外映射 Web 端口
docker compose config --services
docker compose config | grep -A 5 'ports:'
```

预期服务为：

```text
db
backend
web
```

### 6. 构建并启动

推荐使用部署脚本：

```bash
chmod +x scripts/*.sh
bash scripts/deploy.sh
```

等价的完整手工命令：

```bash
docker compose pull
docker compose build --pull
docker compose up -d
docker compose ps
```

启动过程如下：

1. `db` 启动并通过 `pg_isready` 健康检查。
2. `backend` 自动执行 `alembic upgrade head`，然后启动 FastAPI。
3. `web` 在后端健康后启动 Nginx。

首次拉取镜像和编译前端可能需要数分钟。

### 7. 验证部署

```bash
# 查看容器状态
docker compose ps

# 验证 Nginx
curl --fail --show-error http://127.0.0.1/nginx-health

# 验证后端和数据库连接
curl --fail --show-error http://127.0.0.1/api/health

# 使用项目健康检查脚本，最长等待 60 秒
APP_BASE_URL=http://127.0.0.1 bash scripts/health-check.sh
```

健康接口预期返回类似内容：

```json
{"status":"ok","service":"esports-site-selection","database":"connected"}
```

浏览器访问：

```text
http://服务器公网IP/
```

### 8. 配置防火墙

如果服务器启用了 UFW：

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw status
```

如果把 `WEB_PORT` 改成其他端口，例如 `8080`：

```bash
sudo ufw allow 8080/tcp
curl http://127.0.0.1:8080/api/health
```

还需要在云服务器安全组中开放相同端口。不要开放 PostgreSQL 的 `5432` 端口。

## 日志和状态检查

```bash
cd /opt/esports-site-selection/app

# 所有服务最近 200 行日志
docker compose logs --tail=200

# 持续查看 Web 和后端日志
docker compose logs -f --tail=100 web backend

# 单独查看数据库日志
docker compose logs --tail=200 db

# 查看容器和健康状态
docker compose ps
docker inspect --format='{{json .State.Health}}' "$(docker compose ps -q backend)"

# 查看资源占用
docker stats --no-stream

# 查看磁盘占用
docker system df
docker volume ls
```

## 更新部署

更新前先备份数据库：

```bash
cd /opt/esports-site-selection/app
bash scripts/backup-db.sh
git status --short
git pull --ff-only
bash scripts/deploy.sh
APP_BASE_URL=http://127.0.0.1 bash scripts/health-check.sh
```

`scripts/deploy.sh` 不会执行 `docker compose down -v`，不会删除数据库或数据卷。

如果只修改了后端：

```bash
docker compose build --pull backend
docker compose up -d backend
docker compose logs -f --tail=100 backend
```

如果修改了前端或高德 JavaScript 配置：

```bash
docker compose build --pull web
docker compose up -d web
docker compose logs -f --tail=100 web
```

## 数据库备份与恢复

### 创建备份

```bash
cd /opt/esports-site-selection/app
chmod +x scripts/backup-db.sh
bash scripts/backup-db.sh
ls -lh backups/
```

备份文件格式为：

```text
backups/site_selection_YYYYMMDD_HHMMSS.sql.gz
```

建议将备份同步到另一台服务器或对象存储，不要只保存在当前服务器。

### 验证备份内容

```bash
gzip -t backups/site_selection_YYYYMMDD_HHMMSS.sql.gz
zcat backups/site_selection_YYYYMMDD_HHMMSS.sql.gz | head -n 20
```

### 恢复备份

恢复会修改数据库，必须先停止 Web 和后端，并确认备份文件正确：

```bash
cd /opt/esports-site-selection/app
set -a
source .env
set +a

docker compose stop web backend
zcat backups/site_selection_YYYYMMDD_HHMMSS.sql.gz \
  | docker compose exec -T db psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"
docker compose start backend web
APP_BASE_URL=http://127.0.0.1 bash scripts/health-check.sh
```

生产恢复前应先在独立测试数据库验证备份。若目标库已有冲突对象，不能直接覆盖，应由数据库管理员制定清库或定向恢复方案。

## 停止和重新启动

```bash
# 停止容器但保留容器、数据库和数据卷
docker compose stop

# 重新启动
docker compose start

# 删除容器和网络，但保留命名数据卷
docker compose down

# 重新创建容器，仍使用原数据卷
docker compose up -d
```

禁止在生产环境执行以下命令，除非明确要永久删除全部数据库数据：

```bash
docker compose down -v
docker volume rm esports-site-selection_postgres_data
```

## 常见问题排查

### `docker compose` 命令不存在

```bash
docker compose version
sudo apt-get update
sudo apt-get install -y docker-compose-plugin
```

### 当前用户没有 Docker 权限

典型错误：`permission denied while trying to connect to the Docker daemon socket`。

```bash
sudo usermod -aG docker "$USER"
newgrp docker
docker ps
```

### 数据库未通过健康检查

```bash
docker compose ps db
docker compose logs --tail=200 db
docker compose exec db pg_isready -U site_selection -d site_selection
```

重点检查 `.env` 中 `POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB` 和 `DATABASE_URL` 是否一致。

### 后端启动失败

```bash
docker compose ps backend
docker compose logs --tail=300 backend
docker compose run --rm backend alembic current
docker compose run --rm backend alembic upgrade head
```

### 前端可以打开，但 API 返回 `502 Bad Gateway`

```bash
docker compose ps backend web
docker compose logs --tail=200 backend web
docker compose exec web wget -qO- http://backend:8000/api/health
```

### 高德接口失败

```bash
# 只确认变量是否非空，不输出真实 Key
docker compose exec backend python -c \
  "import os; print('configured' if os.getenv('AMAP_WEB_SERVICE_KEY') else 'missing')"

docker compose logs --tail=200 backend
```

检查高德控制台中的 Key 类型、配额、白名单和安全配置。日志中不应打印完整 Key。

### 修改 `.env` 后配置没有生效

后端配置修改后重新创建容器：

```bash
docker compose up -d --force-recreate backend
```

前端 `VITE_AMAP_*` 是构建参数，必须重新构建：

```bash
docker compose build --no-cache web
docker compose up -d web
```

## HTTPS 建议

当前 Compose 默认提供 HTTP。正式公网部署建议在服务器入口增加 HTTPS，可使用云负载均衡、Caddy，或安装 Certbot 后扩展 Nginx 配置。启用 HTTPS 后，应把 `APP_BASE_URL` 修改为实际 `https://` 域名，并只在防火墙开放 `80/443`。

## 本地开发

### 后端

Linux/macOS：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
pytest -q
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Windows PowerShell：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
pytest -q
uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd frontend
npm install
npm test
npm run build
npm run dev
```

开发服务器默认访问 `http://localhost:5173/`，并将 `/api` 代理到 `http://localhost:8000`。

## 可选 Basic Auth

测试环境可在 `deploy/nginx.conf` 的 `server` 中增加：

```nginx
auth_basic "Test Environment";
auth_basic_user_file /etc/nginx/.htpasswd;
```

然后以只读 volume 挂载 `.htpasswd`。不要把密码文件提交到仓库。生产环境更建议使用统一身份认证或网关鉴权。

## 更多文档

- [产品说明](docs/PRODUCT.md)
- [系统架构](docs/ARCHITECTURE.md)
- [数据模型](docs/DATA_MODEL.md)
- [评分模型](docs/SCORING_MODEL.md)
- [部署说明](docs/DEPLOYMENT.md)
- [API](docs/API.md)
- [路线图](docs/ROADMAP.md)
- [决策记录](docs/DECISIONS.md)
