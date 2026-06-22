# 直接部署架构

生产默认直接部署在 Ubuntu：Nginx 监听公网端口并托管 `frontend/dist`，`/api` 反向代理到仅监听 `127.0.0.1:8000` 的 FastAPI；FastAPI 由 systemd 管理，通过本机 `127.0.0.1:5432` 访问 PostgreSQL/PostGIS。

完整命令见项目根目录 `README.md`。核心脚本：

- `scripts/bootstrap-ubuntu-direct.sh`：检查并安装 Python、Node.js、Nginx、PostgreSQL/PostGIS。
- `scripts/deploy.sh`：安装依赖、构建前端、迁移数据库、安装 systemd/Nginx 配置并执行健康检查。
- `scripts/backup-db.sh`：使用本机 `pg_dump` 生成压缩备份。
- `scripts/health-check.sh`：轮询 `/api/health`。

配置与密钥存储在 `/etc/esports-site-selection/backend.env`，权限必须为 `root:esports-site-selection 0640`。数据库和 Uvicorn 端口不得暴露公网。

Docker Compose 文件仅作为可选部署方式保留，不是默认生产路径。
