#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="esports-site-selection"
CONFIG_DIR="/etc/esports-site-selection"
DATA_DIR="/var/lib/esports-site-selection"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
NGINX_AVAILABLE="/etc/nginx/sites-available/esports-site-selection"
NGINX_ENABLED="/etc/nginx/sites-enabled/esports-site-selection"
MODE="safe"

case "${1:-}" in
  "") ;;
  --purge) MODE="purge" ;;
  --purge-all) MODE="purge-all" ;;
  *) echo "Usage: sudo ./uninstall.sh [--purge|--purge-all]" >&2; exit 2 ;;
esac

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: 卸载需要 root 权限，请执行：sudo ./uninstall.sh" >&2
  exit 1
fi

log() { echo "==> $*"; }

log "停止并禁用后端服务"
systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
rm -f "${SERVICE_FILE}"
systemctl daemon-reload

log "删除 Nginx 配置"
rm -f "${NGINX_ENABLED}" "${NGINX_AVAILABLE}"
if command -v nginx >/dev/null 2>&1; then
  nginx -t && systemctl reload nginx || true
fi

log "删除本项目构建产物"
rm -rf "${APP_ROOT}/backend/.venv"
rm -rf "${APP_ROOT}/frontend/dist"

if [[ "${MODE}" == "purge" || "${MODE}" == "purge-all" ]]; then
  log "彻底删除配置和运行数据"
  rm -rf "${CONFIG_DIR}" "${DATA_DIR}"
else
  echo "保留配置：${CONFIG_DIR}"
  echo "保留 ${DATA_DIR}"
fi

if [[ "${MODE}" == "purge-all" ]]; then
  echo
  echo "警告：即将删除 site_selection 数据库和用户。"
  read -r -p "请输入 DELETE_DATABASE 确认: " db_confirm || true
  [[ "${db_confirm}" == "DELETE_DATABASE" ]] || {
    echo "未确认删除数据库，数据库继续保留。"
    echo "卸载完成。"
    exit 0
  }
  if command -v psql >/dev/null 2>&1 && id postgres >/dev/null 2>&1; then
    sudo -u postgres psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='site_selection';" || true
    sudo -u postgres psql -c "DROP DATABASE IF EXISTS site_selection;"
    sudo -u postgres psql -c "DROP USER IF EXISTS site_selection;"
    echo "已删除数据库 site_selection 和用户 site_selection"
  else
    echo "未找到 PostgreSQL/psql，跳过数据库删除"
  fi
fi

if [[ "${MODE}" != "purge-all" ]]; then
  echo "保留数据库 site_selection"
fi

echo
echo "卸载完成。"
if [[ "${MODE}" == "safe" ]]; then
  echo "重新安装只需执行：sudo ./install.sh"
fi
