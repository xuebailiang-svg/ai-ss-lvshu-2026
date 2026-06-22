# 部署与运维

按 README 复制并填写 `.env` 后执行 `docker compose up -d --build`。服务包括 `db`（PostGIS）、`backend`（迁移后启动 FastAPI）、`web`（Nginx 与静态前端）。健康检查为 `/api/health`。诊断命令：`docker compose config`、`docker compose ps`、`docker compose logs --tail=200 backend`。备份使用 `scripts/backup-db.sh`，恢复前应先创建独立测试库验证备份。部署脚本不会执行 `down -v` 或删除数据卷。
