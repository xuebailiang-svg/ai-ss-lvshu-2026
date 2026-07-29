#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="${ESPORTS_APP_ROOT:-/opt/esports-site-selection/app/ai-ss-lvshu-2026-main}"
CRAWLER_ROOT="${ESPORTS_CRAWLER_ROOT:-/opt/esports-site-selection/crawler}"
APP_USER="esports-site-selection"
APP_GROUP="esports-site-selection"
DATA_DIR="/var/lib/esports-site-selection"
CRAWLER_DATA_DIR="${DATA_DIR}/crawler"
LEGACY_BROWSER_DIR="${DATA_DIR}/.cache/ms-playwright"
ENV_FILE="/etc/esports-site-selection/backend.env"
SERVICE_NAME="esports-site-selection-crawler"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
BUNDLE=""

usage() {
  cat <<EOF
用法：
  sudo bash scripts/crawler/install.sh
  sudo bash scripts/crawler/install.sh --bundle /path/esports-crawler-offline-ubuntu22.04-amd64.tar.gz
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bundle) BUNDLE="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: 未知参数 $1" >&2; usage; exit 2 ;;
  esac
done

[[ "${EUID}" -eq 0 ]] || { echo "ERROR: 请使用 sudo 执行" >&2; exit 1; }
[[ -d "${APP_ROOT}/backend/app" ]] || {
  echo "ERROR: 主系统未部署到 ${APP_ROOT}，请先执行 sudo ./install.sh" >&2
  exit 1
}
[[ -f "${ENV_FILE}" ]] || { echo "ERROR: 缺少 ${ENV_FILE}" >&2; exit 1; }
id "${APP_USER}" >/dev/null 2>&1 || { echo "ERROR: 缺少运行用户 ${APP_USER}" >&2; exit 1; }

install -d -m 0750 -o "${APP_USER}" -g "${APP_GROUP}" "${CRAWLER_DATA_DIR}"
install -d -m 0755 -o root -g root "${CRAWLER_ROOT}"
rm -rf "${CRAWLER_ROOT}/.venv"
python3 -m venv "${CRAWLER_ROOT}/.venv"

if [[ ! -d "${CRAWLER_DATA_DIR}/ms-playwright" ]] && compgen -G "${LEGACY_BROWSER_DIR}/chromium-*" >/dev/null; then
  echo "==> 复用主系统旧版 Playwright 浏览器缓存"
  cp -a "${LEGACY_BROWSER_DIR}" "${CRAWLER_DATA_DIR}/ms-playwright"
fi

if [[ -n "${BUNDLE}" ]]; then
  [[ -f "${BUNDLE}" ]] || { echo "ERROR: 找不到离线包 ${BUNDLE}" >&2; exit 1; }
  WORK_DIR="$(mktemp -d /tmp/esports-crawler-install.XXXXXX)"
  trap 'rm -rf "${WORK_DIR}"' EXIT
  tar -xzf "${BUNDLE}" -C "${WORK_DIR}"
  OFFLINE="${WORK_DIR}/esports-crawler-offline"
  [[ -d "${OFFLINE}/wheelhouse" && -d "${OFFLINE}/ms-playwright" ]] || {
    echo "ERROR: 离线包结构不正确" >&2
    exit 1
  }
  if compgen -G "${OFFLINE}/debs/*.deb" >/dev/null; then
    echo "==> 安装离线 Chromium 系统依赖"
    dpkg -i "${OFFLINE}"/debs/*.deb || {
      echo "ERROR: 离线 .deb 依赖不完整。请在同版本 Ubuntu 22.04 构建离线包，或联网执行在线安装。" >&2
      exit 1
    }
  fi
  "${CRAWLER_ROOT}/.venv/bin/pip" install \
    --no-index \
    --find-links "${OFFLINE}/wheelhouse" \
    -r "${APP_ROOT}/backend/requirements.txt" \
    -r "${APP_ROOT}/crawler/requirements.txt"
  rm -rf "${CRAWLER_DATA_DIR}/ms-playwright"
  cp -a "${OFFLINE}/ms-playwright" "${CRAWLER_DATA_DIR}/ms-playwright"
else
  echo "==> 在线安装独立爬虫 Python 依赖"
  "${CRAWLER_ROOT}/.venv/bin/python" -m pip install --upgrade pip
  "${CRAWLER_ROOT}/.venv/bin/pip" install \
    -r "${APP_ROOT}/backend/requirements.txt" \
    -r "${APP_ROOT}/crawler/requirements.txt"
  "${CRAWLER_ROOT}/.venv/bin/python" -m playwright install-deps chromium
  install -d -m 0750 -o "${APP_USER}" -g "${APP_GROUP}" "${CRAWLER_DATA_DIR}/ms-playwright"
  runuser -u "${APP_USER}" -- env HOME="${DATA_DIR}" PLAYWRIGHT_BROWSERS_PATH="${CRAWLER_DATA_DIR}/ms-playwright" \
    "${CRAWLER_ROOT}/.venv/bin/python" -m playwright install chromium
fi

chown -R "${APP_USER}:${APP_GROUP}" "${CRAWLER_ROOT}/.venv" "${CRAWLER_DATA_DIR}"

echo "==> 验证 crawl4ai 和 Chromium"
runuser -u "${APP_USER}" -- env \
  HOME="${DATA_DIR}" \
  PYTHONPATH="${APP_ROOT}/backend" \
  PLAYWRIGHT_BROWSERS_PATH="${CRAWLER_DATA_DIR}/ms-playwright" \
  "${CRAWLER_ROOT}/.venv/bin/python" -c \
  "import crawl4ai; from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); b.close(); p.stop()"

cat >"${SERVICE_FILE}" <<EOF
[Unit]
Description=Esports Site Selection Crawler Worker
After=network-online.target postgresql.service esports-site-selection.service
Wants=network-online.target
Requires=esports-site-selection.service

[Service]
Type=simple
User=${APP_USER}
Group=${APP_GROUP}
WorkingDirectory=${APP_ROOT}/backend
EnvironmentFile=${ENV_FILE}
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONPATH=${APP_ROOT}/backend
Environment=HOME=${DATA_DIR}
Environment=PLAYWRIGHT_BROWSERS_PATH=${CRAWLER_DATA_DIR}/ms-playwright
Environment=CRAWLER_HEALTH_FILE=${CRAWLER_DATA_DIR}/worker-health.json
ExecStart=${CRAWLER_ROOT}/.venv/bin/python -m app.data_source.crawler.worker
Restart=on-failure
RestartSec=5
TimeoutStopSec=60
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=${DATA_DIR}

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}"
sleep 3
systemctl is-active --quiet "${SERVICE_NAME}" || {
  systemctl status "${SERVICE_NAME}" --no-pager -l || true
  exit 1
}
if command -v curl >/dev/null && systemctl is-active --quiet esports-site-selection; then
  curl --fail --silent --show-error --max-time 10 \
    http://127.0.0.1:8000/api/data-sources/crawler/runtime >/dev/null || {
      echo "ERROR: Worker 已启动，但主系统暂未读取到爬虫健康状态" >&2
      exit 1
    }
fi

cat <<EOF
独立爬虫部署完成。

服务状态：
  sudo systemctl status ${SERVICE_NAME} --no-pager -l

运行状态：
  curl http://127.0.0.1/api/data-sources/crawler/runtime

下一步：
  在 Web 配置页启用爬虫，再点击连接测试。
EOF
