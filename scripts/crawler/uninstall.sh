#!/usr/bin/env bash
set -Eeuo pipefail

CRAWLER_ROOT="${ESPORTS_CRAWLER_ROOT:-/opt/esports-site-selection/crawler}"
DATA_DIR="/var/lib/esports-site-selection/crawler"
SERVICE_NAME="esports-site-selection-crawler"
PURGE=false
[[ "${1:-}" == "--purge" ]] && PURGE=true

[[ "${EUID}" -eq 0 ]] || { echo "ERROR: 请使用 sudo 执行" >&2; exit 1; }
systemctl disable --now "${SERVICE_NAME}" 2>/dev/null || true
rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
rm -rf "${CRAWLER_ROOT}/.venv"

if [[ "${PURGE}" == true ]]; then
  rm -rf "${DATA_DIR}"
  echo "独立爬虫已卸载，浏览器缓存和健康状态已删除。"
else
  echo "独立爬虫已卸载；保留 ${DATA_DIR}，使用 --purge 可同时删除。"
fi
