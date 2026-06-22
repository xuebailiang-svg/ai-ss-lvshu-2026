#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE=/etc/esports-site-selection/backend.env
SERVICE_NAME=esports-site-selection

if [[ "${EUID}" -eq 0 ]]; then SUDO=(); else SUDO=(sudo); fi
command -v python3 >/dev/null 2>&1 || { echo "ERROR: 缺少 python3，请先运行 scripts/bootstrap-ubuntu-direct.sh。" >&2; exit 1; }
command -v nginx >/dev/null 2>&1 || { echo "ERROR: 缺少 nginx，请先运行 scripts/bootstrap-ubuntu-direct.sh。" >&2; exit 1; }
[[ -s "${ENV_FILE}" ]] || { echo "ERROR: ${ENV_FILE} 不存在或为空。" >&2; exit 1; }
grep -Eq '^DATABASE_URL=.+$' "${ENV_FILE}" || { echo "ERROR: backend.env 缺少 DATABASE_URL。" >&2; exit 1; }
grep -q 'REPLACE_WITH_PASSWORD' "${ENV_FILE}" && { echo "ERROR: backend.env 仍包含示例密码。" >&2; exit 1; }

echo "[1/6] 创建 Python 虚拟环境并安装后端"
python3 -m venv "${APP_ROOT}/backend/.venv"
"${APP_ROOT}/backend/.venv/bin/python" -m pip install --upgrade pip
"${APP_ROOT}/backend/.venv/bin/pip" install -e "${APP_ROOT}/backend"

echo "[2/6] 安装前端依赖并构建"
if command -v npm >/dev/null 2>&1; then
  npm --prefix "${APP_ROOT}/frontend" install --no-audit --no-fund
  npm --prefix "${APP_ROOT}/frontend" run build
elif [[ -s "${APP_ROOT}/frontend/dist/index.html" ]]; then
  echo "未安装 npm，使用已上传的 frontend/dist。"
else
  echo "ERROR: 缺少 npm 且没有预构建 frontend/dist。" >&2
  exit 1
fi
test -s "${APP_ROOT}/frontend/dist/index.html"

echo "[3/6] 执行数据库迁移"
"${SUDO[@]}" runuser -u esports-site-selection -- bash -c \
  "set -a; source '${ENV_FILE}'; set +a; cd '${APP_ROOT}/backend'; .venv/bin/alembic upgrade head"

echo "[4/6] 安装 systemd 服务"
service_tmp="$(mktemp)"
nginx_tmp="$(mktemp)"
trap 'rm -f "${service_tmp}" "${nginx_tmp}"' EXIT
sed "s|__APP_ROOT__|${APP_ROOT}|g" "${APP_ROOT}/deploy/systemd/esports-site-selection.service" >"${service_tmp}"
"${SUDO[@]}" install -m 0644 "${service_tmp}" /etc/systemd/system/esports-site-selection.service
"${SUDO[@]}" systemctl daemon-reload
"${SUDO[@]}" systemctl enable --now "${SERVICE_NAME}"
"${SUDO[@]}" systemctl restart "${SERVICE_NAME}"

echo "[5/6] 安装并验证 Nginx 配置"
sed "s|__APP_ROOT__|${APP_ROOT}|g" "${APP_ROOT}/deploy/nginx-direct.conf" >"${nginx_tmp}"
"${SUDO[@]}" install -m 0644 "${nginx_tmp}" /etc/nginx/sites-available/esports-site-selection
"${SUDO[@]}" ln -sfn /etc/nginx/sites-available/esports-site-selection /etc/nginx/sites-enabled/esports-site-selection
"${SUDO[@]}" rm -f /etc/nginx/sites-enabled/default
"${SUDO[@]}" nginx -t
"${SUDO[@]}" systemctl reload nginx

echo "[6/6] 检查服务"
"${SUDO[@]}" systemctl is-active --quiet "${SERVICE_NAME}"
"${SUDO[@]}" systemctl is-active --quiet nginx
APP_BASE_URL=http://127.0.0.1 bash "${APP_ROOT}/scripts/health-check.sh"
echo "直接部署完成：http://服务器IP/"
