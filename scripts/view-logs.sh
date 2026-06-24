#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE_NAME="${SERVICE_NAME:-esports-site-selection}"
LINES="${LINES:-200}"
TARGET="${1:-all}"
MODE="${2:-recent}"

if [[ "${EUID}" -eq 0 ]]; then
  SUDO=()
else
  SUDO=(sudo)
fi

usage() {
  cat <<EOF
用法：
  bash scripts/view-logs.sh [backend|nginx|all] [recent|follow]

示例：
  bash scripts/view-logs.sh
  bash scripts/view-logs.sh backend
  bash scripts/view-logs.sh nginx
  bash scripts/view-logs.sh backend follow

环境变量：
  LINES=200
  SERVICE_NAME=esports-site-selection
EOF
}

show_backend_recent() {
  echo "---- backend journal: ${SERVICE_NAME}, last ${LINES} lines ----"
  "${SUDO[@]}" journalctl -u "${SERVICE_NAME}" -n "${LINES}" --no-pager
}

show_backend_follow() {
  echo "---- backend journal follow: ${SERVICE_NAME} ----"
  "${SUDO[@]}" journalctl -u "${SERVICE_NAME}" -f
}

show_nginx_recent() {
  echo "---- nginx error.log, last ${LINES} lines ----"
  "${SUDO[@]}" tail -n "${LINES}" /var/log/nginx/error.log || true
  echo
  echo "---- nginx access.log, last ${LINES} lines ----"
  "${SUDO[@]}" tail -n "${LINES}" /var/log/nginx/access.log || true
}

show_nginx_follow() {
  echo "---- nginx logs follow: error.log + access.log ----"
  "${SUDO[@]}" tail -f /var/log/nginx/error.log /var/log/nginx/access.log
}

case "${TARGET}" in
  -h|--help|help)
    usage
    exit 0
    ;;
  backend)
    if [[ "${MODE}" == "follow" ]]; then show_backend_follow; else show_backend_recent; fi
    ;;
  nginx)
    if [[ "${MODE}" == "follow" ]]; then show_nginx_follow; else show_nginx_recent; fi
    ;;
  all)
    if [[ "${MODE}" == "follow" ]]; then
      echo "ERROR: all follow 容易混淆输出，请分别执行 backend follow 或 nginx follow。" >&2
      exit 2
    fi
    show_backend_recent
    echo
    show_nginx_recent
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
