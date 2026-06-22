# 电竞馆智能选址系统 M1

面向电竞馆投资与运营人员的候选地址初筛系统。M1 支持地址地理编码、周边 POI、物业调查、合规风险、规则评分、报告和历史记录。系统结论仅用于初步筛查，最终以当地主管部门要求为准。

## Ubuntu 部署

要求 Docker Engine 24+ 与 Docker Compose v2。

```bash
cp .env.example .env
# 编辑 .env：必须修改数据库密码并填写 AMAP_WEB_SERVICE_KEY
docker compose up -d --build
docker compose ps
curl http://localhost/api/health
```

浏览器访问 `http://服务器IP/`。查看日志：`docker compose logs -f backend web db`。备份：`bash scripts/backup-db.sh`。更新部署可执行 `bash scripts/deploy.sh`，脚本不会删除数据库或数据卷。

无高德 Key 的演示环境可设置 `AMAP_MOCK=true`。生产环境必须改为 `false` 并配置真实 Key。

## 本地开发

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -e ".[test]"
.venv/Scripts/pytest
uvicorn app.main:app --reload

cd ../frontend
npm ci
npm test
npm run dev
```

可选 Basic Auth：在 `deploy/nginx.conf` 的 `server` 中加入 `auth_basic "Test Environment"; auth_basic_user_file /etc/nginx/.htpasswd;`，并通过只读 volume 挂载密码文件。不要把密码文件提交到仓库。

详见 [部署](docs/DEPLOYMENT.md)、[API](docs/API.md) 和 [架构](docs/ARCHITECTURE.md)。
