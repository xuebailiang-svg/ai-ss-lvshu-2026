#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE_NAME="esports-site-selection"

if [[ "${EUID}" -eq 0 ]]; then
  SUDO=()
else
  SUDO=(sudo)
fi

echo "启动后端服务：${SERVICE_NAME}"
"${SUDO[@]}" systemctl start "${SERVICE_NAME}"
"${SUDO[@]}" systemctl is-active --quiet "${SERVICE_NAME}"

echo "启动 Nginx"
"${SUDO[@]}" systemctl start nginx
"${SUDO[@]}" systemctl is-active --quiet nginx

echo "服务已启动"
echo "Backend health:  curl http://127.0.0.1:8000/api/system/health"
echo "Frontend:        http://服务器公网IP/"
