#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE_NAME="esports-site-selection"

if [[ "${EUID}" -eq 0 ]]; then
  SUDO=()
else
  SUDO=(sudo)
fi

echo "停止后端服务：${SERVICE_NAME}"
"${SUDO[@]}" systemctl stop "${SERVICE_NAME}" || true

echo "停止 Nginx"
"${SUDO[@]}" systemctl stop nginx || true

echo "服务已停止"
