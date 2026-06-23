#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE=/etc/esports-site-selection/backend.env
SERVICE_NAME=esports-site-selection

if [[ "${EUID}" -eq 0 ]]; then
  SUDO=()
else
  SUDO=(sudo)
fi

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

print_backend_diagnostics() {
  echo "---- systemctl status ${SERVICE_NAME} ----" >&2
  "${SUDO[@]}" systemctl status "${SERVICE_NAME}" --no-pager >&2 || true
  echo "---- journalctl -u ${SERVICE_NAME} -n 100 ----" >&2
  "${SUDO[@]}" journalctl -u "${SERVICE_NAME}" -n 100 --no-pager >&2 || true
}

wait_for_url() {
  local name="$1"
  local url="$2"
  local max_attempts="${3:-30}"
  local attempt
  for attempt in $(seq 1 "${max_attempts}"); do
    if curl --fail --silent --show-error --max-time 5 "${url}" >/tmp/esports-healthcheck.out 2>/tmp/esports-healthcheck.err; then
      echo "OK: ${name} ready (${url})"
      rm -f /tmp/esports-healthcheck.out /tmp/esports-healthcheck.err
      return 0
    fi
    echo "等待 ${name} ready：${attempt}/${max_attempts}"
    sleep 1
  done

  echo "ERROR: ${name} health check failed: ${url}" >&2
  if [[ -s /tmp/esports-healthcheck.err ]]; then
    cat /tmp/esports-healthcheck.err >&2
  fi
  if [[ -s /tmp/esports-healthcheck.out ]]; then
    cat /tmp/esports-healthcheck.out >&2
  fi
  rm -f /tmp/esports-healthcheck.out /tmp/esports-healthcheck.err
  return 1
}

check_env_file() {
  if ! "${SUDO[@]}" test -e "${ENV_FILE}"; then
    fail "${ENV_FILE} 不存在。请先运行 scripts/configure-secrets.sh，或按 README 创建后端配置。"
  fi
  if ! "${SUDO[@]}" test -f "${ENV_FILE}"; then
    fail "${ENV_FILE} 不是普通文件。"
  fi
  if ! "${SUDO[@]}" test -s "${ENV_FILE}"; then
    fail "${ENV_FILE} 是空文件。请写入 DATABASE_URL 等配置。"
  fi
  if ! "${SUDO[@]}" test -r "${ENV_FILE}"; then
    fail "${ENV_FILE} 权限不足，当前用户或 sudo 无法读取。请检查 owner/group/mode。"
  fi
  if [[ ! -r "${ENV_FILE}" ]]; then
    echo "WARNING: 当前 shell 用户无法直接读取 ${ENV_FILE}。"
    echo "         部署脚本会通过 sudo 读取；如需当前用户直接读取，请重新登录或执行："
    echo "         sg esports-site-selection -c 'cd ${APP_ROOT} && bash scripts/deploy.sh'"
  fi
  "${SUDO[@]}" grep -Eq '^DATABASE_URL=.+$' "${ENV_FILE}" || fail "backend.env 缺少 DATABASE_URL。"
  if "${SUDO[@]}" grep -q 'REPLACE_WITH_PASSWORD' "${ENV_FILE}"; then
    fail "backend.env 仍包含示例密码 REPLACE_WITH_PASSWORD。"
  fi
}

command -v python3 >/dev/null 2>&1 || fail "缺少 python3，请先运行 scripts/bootstrap-ubuntu-direct.sh。"
command -v nginx >/dev/null 2>&1 || fail "缺少 nginx，请先运行 scripts/bootstrap-ubuntu-direct.sh。"
command -v curl >/dev/null 2>&1 || fail "缺少 curl，请先运行 scripts/bootstrap-ubuntu-direct.sh。"
id esports-site-selection >/dev/null 2>&1 || fail "缺少系统用户 esports-site-selection，请先运行 scripts/bootstrap-ubuntu-direct.sh。"
check_env_file

echo "[1/6] 创建 Python 虚拟环境并安装后端"
python3 -m venv "${APP_ROOT}/backend/.venv"
"${APP_ROOT}/backend/.venv/bin/python" -m pip install --upgrade pip
"${APP_ROOT}/backend/.venv/bin/pip" install -e "${APP_ROOT}/backend"

echo "[2/6] 安装前端依赖并构建"
if command -v npm >/dev/null 2>&1; then
  npm --prefix "${APP_ROOT}/frontend" install --no-audit --no-fund
  npm --prefix "${APP_ROOT}/frontend" run build
elif [[ -s "${APP_ROOT}/frontend/dist/index.html" ]]; then
  echo "未安装 npm，使用已存在的 frontend/dist。"
else
  fail "缺少 npm 且没有预构建 frontend/dist。"
fi
test -s "${APP_ROOT}/frontend/dist/index.html" || fail "frontend/dist/index.html 不存在，前端构建失败。"

echo "[3/6] 执行数据库迁移"
"${SUDO[@]}" runuser -u esports-site-selection -- bash -c \
  "set -a; source '${ENV_FILE}'; set +a; cd '${APP_ROOT}/backend'; .venv/bin/alembic upgrade head"

echo "[4/6] 安装并启动 systemd 后端服务"
service_tmp="$(mktemp)"
nginx_tmp="$(mktemp)"
trap 'rm -f "${service_tmp}" "${nginx_tmp}"' EXIT
sed "s|__APP_ROOT__|${APP_ROOT}|g" "${APP_ROOT}/deploy/systemd/esports-site-selection.service" >"${service_tmp}"
"${SUDO[@]}" install -m 0644 "${service_tmp}" /etc/systemd/system/esports-site-selection.service
"${SUDO[@]}" systemctl daemon-reload
"${SUDO[@]}" systemctl enable --now "${SERVICE_NAME}"
"${SUDO[@]}" systemctl restart "${SERVICE_NAME}"
"${SUDO[@]}" systemctl is-active --quiet "${SERVICE_NAME}" || { print_backend_diagnostics; exit 1; }
wait_for_url "后端" "http://127.0.0.1:8000/api/health" 30 || { print_backend_diagnostics; exit 1; }

echo "[5/6] 安装并验证 Nginx 配置"
sed "s|__APP_ROOT__|${APP_ROOT}|g" "${APP_ROOT}/deploy/nginx-direct.conf" >"${nginx_tmp}"
"${SUDO[@]}" install -m 0644 "${nginx_tmp}" /etc/nginx/sites-available/esports-site-selection
"${SUDO[@]}" ln -sfn /etc/nginx/sites-available/esports-site-selection /etc/nginx/sites-enabled/esports-site-selection
"${SUDO[@]}" rm -f /etc/nginx/sites-enabled/default
"${SUDO[@]}" nginx -t
"${SUDO[@]}" systemctl reload nginx
"${SUDO[@]}" systemctl is-active --quiet nginx

echo "[6/6] 检查服务"
wait_for_url "Nginx 静态健康检查" "http://127.0.0.1/nginx-health" 30 || exit 1
wait_for_url "Nginx API 反向代理" "http://127.0.0.1/api/health" 30 || { print_backend_diagnostics; exit 1; }
curl --fail --silent --show-error --head "http://127.0.0.1/" >/dev/null
echo "直接部署完成：http://服务器公网IP/"
