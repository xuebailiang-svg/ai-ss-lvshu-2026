#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="esports-site-selection"
CONFIG_DIR="/etc/esports-site-selection"
DATA_DIR="/var/lib/esports-site-selection"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
NGINX_AVAILABLE="/etc/nginx/sites-available/esports-site-selection"
NGINX_ENABLED="/etc/nginx/sites-enabled/esports-site-selection"

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: 卸载需要 root 权限，请执行：sudo ./uninstall.sh" >&2
  exit 1
fi

log() { echo "==> $*"; }

confirm_yes() {
  local prompt="$1" value
  read -r -p "${prompt} [y/N]: " value || true
  [[ "${value}" == "y" || "${value}" == "Y" ]]
}

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

log "删除配置目录"
rm -rf "${CONFIG_DIR}"

if confirm_yes "是否删除 trace/feedback 运行数据目录 ${DATA_DIR}"; then
  if confirm_yes "再次确认删除 ${DATA_DIR}，该操作不可恢复"; then
    rm -rf "${DATA_DIR}"
    echo "已删除 ${DATA_DIR}"
  else
    echo "保留 ${DATA_DIR}"
  fi
else
  echo "保留 ${DATA_DIR}"
fi

echo
echo "数据库默认保留。只有输入 DELETE_DATABASE 才会删除 site_selection 数据库和用户。"
read -r -p "如需删除数据库和用户，请输入 DELETE_DATABASE: " db_confirm || true
if [[ "${db_confirm}" == "DELETE_DATABASE" ]]; then
  if command -v psql >/dev/null 2>&1 && id postgres >/dev/null 2>&1; then
    sudo -u postgres psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='site_selection';" || true
    sudo -u postgres psql -c "DROP DATABASE IF EXISTS site_selection;"
    sudo -u postgres psql -c "DROP USER IF EXISTS site_selection;"
    echo "已删除数据库 site_selection 和用户 site_selection"
  else
    echo "未找到 PostgreSQL/psql，跳过数据库删除"
  fi
else
  echo "保留数据库 site_selection"
fi

echo "卸载完成。"
