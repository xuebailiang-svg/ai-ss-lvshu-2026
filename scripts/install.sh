#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_NAME="esports-site-selection"
APP_USER="esports-site-selection"
CONFIG_DIR="/etc/esports-site-selection"
ENV_FILE="${CONFIG_DIR}/backend.env"
FRONTEND_RUNTIME_FILE="${CONFIG_DIR}/frontend-runtime.json"
DATA_DIR="/var/lib/esports-site-selection"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
NGINX_SITE="/etc/nginx/sites-available/esports-site-selection"

if [[ "${EUID}" -eq 0 ]]; then
  SUDO=()
else
  SUDO=(sudo)
fi

log() {
  echo "==> $*"
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

need_command() {
  command -v "$1" >/dev/null 2>&1 || fail "缺少命令：$1。请先安装后重试。"
}

wait_for_url() {
  local name="$1"
  local url="$2"
  local max_attempts="${3:-30}"
  local attempt
  for attempt in $(seq 1 "${max_attempts}"); do
    if curl --fail --silent --show-error --max-time 5 "${url}" >/dev/null; then
      echo "OK: ${name} ready (${url})"
      return 0
    fi
    echo "等待 ${name} ready：${attempt}/${max_attempts}"
    sleep 1
  done
  return 1
}

ensure_user() {
  if id "${APP_USER}" >/dev/null 2>&1; then
    return 0
  fi
  log "创建系统用户 ${APP_USER}"
  "${SUDO[@]}" useradd --system --home "${DATA_DIR}" --shell /usr/sbin/nologin "${APP_USER}"
}

ensure_env_files() {
  log "初始化配置文件"
  "${SUDO[@]}" install -d -m 0750 -o root -g "${APP_USER}" "${CONFIG_DIR}"
  "${SUDO[@]}" install -d -m 0750 -o "${APP_USER}" -g "${APP_USER}" "${DATA_DIR}"

  if [[ ! -f "${APP_ROOT}/.env" ]]; then
    cp "${APP_ROOT}/.env.example" "${APP_ROOT}/.env"
    echo "已创建 ${APP_ROOT}/.env"
  fi

  if ! "${SUDO[@]}" test -s "${ENV_FILE}"; then
    local env_tmp
    env_tmp="$(mktemp)"
    cat >"${env_tmp}" <<EOF
APP_ENV=production
DATABASE_URL=sqlite:////var/lib/esports-site-selection/site_selection.db
AMAP_WEB_SERVICE_KEY=
AMAP_MOCK=false
SCORING_CONFIG_PATH=app/scoring/default.yaml
ENABLE_TRACE=true
ENABLE_FEEDBACK=true
ENABLE_REFLECTION=true
ENABLE_SIMILAR_CASES=true
ENABLE_DEBUG_API=false
ENABLE_DEBUG_ENDPOINTS=false
SITE_FEEDBACK_STORE_PATH=/var/lib/esports-site-selection/site_feedback.json
AGENT_TRACE_STORE_PATH=/var/lib/esports-site-selection/agent_traces.json
EOF
    "${SUDO[@]}" install -m 0640 -o root -g "${APP_USER}" "${env_tmp}" "${ENV_FILE}"
    rm -f "${env_tmp}"
    echo "已创建 ${ENV_FILE}"
  else
    echo "保留已有 ${ENV_FILE}"
  fi

  if ! "${SUDO[@]}" test -s "${FRONTEND_RUNTIME_FILE}"; then
    "${SUDO[@]}" install -m 0644 -o root -g "${APP_USER}" \
      "${APP_ROOT}/deploy/frontend-runtime.example.json" "${FRONTEND_RUNTIME_FILE}"
    echo "已创建 ${FRONTEND_RUNTIME_FILE}"
  else
    echo "保留已有 ${FRONTEND_RUNTIME_FILE}"
  fi
}

init_data_files() {
  log "初始化数据文件"
  "${SUDO[@]}" install -d -m 0750 -o "${APP_USER}" -g "${APP_USER}" "${DATA_DIR}"
  for file in site_feedback.json agent_traces.json; do
    if ! "${SUDO[@]}" test -f "${DATA_DIR}/${file}"; then
      if [[ "${file}" == "site_feedback.json" ]]; then
        echo '{"events":[]}' | "${SUDO[@]}" tee "${DATA_DIR}/${file}" >/dev/null
      else
        echo '{"traces":{}}' | "${SUDO[@]}" tee "${DATA_DIR}/${file}" >/dev/null
      fi
    fi
    "${SUDO[@]}" chown "${APP_USER}:${APP_USER}" "${DATA_DIR}/${file}"
    "${SUDO[@]}" chmod 0640 "${DATA_DIR}/${file}"
  done

  mkdir -p "${APP_ROOT}/data"
  [[ -f "${APP_ROOT}/data/site_feedback.json" ]] || printf '{"events":[]}\n' >"${APP_ROOT}/data/site_feedback.json"
  [[ -f "${APP_ROOT}/data/agent_traces.json" ]] || printf '{"traces":{}}\n' >"${APP_ROOT}/data/agent_traces.json"
}

install_backend() {
  log "部署后端"
  python3 -m venv "${APP_ROOT}/backend/.venv"
  "${APP_ROOT}/backend/.venv/bin/python" -m pip install --upgrade pip
  "${APP_ROOT}/backend/.venv/bin/pip" install -r "${APP_ROOT}/backend/requirements.txt"
  "${APP_ROOT}/backend/.venv/bin/pip" install -e "${APP_ROOT}/backend"

  log "执行数据库迁移"
  "${SUDO[@]}" runuser -u "${APP_USER}" -- bash -c \
    "set -a; source '${ENV_FILE}'; set +a; cd '${APP_ROOT}/backend'; .venv/bin/alembic upgrade head"
}

install_frontend() {
  log "部署前端"
  npm --prefix "${APP_ROOT}/frontend" install --no-audit --no-fund
  npm --prefix "${APP_ROOT}/frontend" run build
  test -s "${APP_ROOT}/frontend/dist/index.html" || fail "frontend/dist/index.html 不存在，前端构建失败。"
}

install_systemd() {
  log "安装 systemd 服务"
  local service_tmp
  service_tmp="$(mktemp)"
  sed "s|__APP_ROOT__|${APP_ROOT}|g" "${APP_ROOT}/deploy/systemd/esports-site-selection.service" >"${service_tmp}"
  "${SUDO[@]}" install -m 0644 "${service_tmp}" "${SERVICE_FILE}"
  rm -f "${service_tmp}"
  "${SUDO[@]}" systemctl daemon-reload
  "${SUDO[@]}" systemctl enable "${SERVICE_NAME}"
  "${SUDO[@]}" systemctl restart "${SERVICE_NAME}"
}

install_nginx() {
  log "安装 Nginx 配置"
  local nginx_tmp
  nginx_tmp="$(mktemp)"
  sed "s|__APP_ROOT__|${APP_ROOT}|g" "${APP_ROOT}/deploy/nginx-direct.conf" >"${nginx_tmp}"
  "${SUDO[@]}" install -m 0644 "${nginx_tmp}" "${NGINX_SITE}"
  rm -f "${nginx_tmp}"
  "${SUDO[@]}" ln -sfn "${NGINX_SITE}" /etc/nginx/sites-enabled/esports-site-selection
  "${SUDO[@]}" rm -f /etc/nginx/sites-enabled/default
  "${SUDO[@]}" nginx -t
  "${SUDO[@]}" systemctl enable nginx
  "${SUDO[@]}" systemctl restart nginx
}

main() {
  log "检查环境"
  need_command python3
  need_command node
  need_command npm
  need_command curl
  need_command systemctl
  need_command nginx

  ensure_user
  ensure_env_files
  init_data_files
  install_backend
  install_frontend
  install_systemd
  install_nginx

  log "验证服务"
  wait_for_url "backend health" "http://127.0.0.1:8000/api/system/health" 30 || fail "后端健康检查失败"
  wait_for_url "frontend" "http://127.0.0.1/" 30 || fail "前端访问失败"
  wait_for_url "nginx api proxy" "http://127.0.0.1/api/system/health" 30 || fail "Nginx API 反向代理失败"

  cat <<EOF

部署完成。

Backend URL:
  http://127.0.0.1:8000

Frontend URL:
  http://服务器公网IP/

Health check:
  curl http://127.0.0.1:8000/api/system/health
  curl http://127.0.0.1/api/system/health

配置文件:
  ${ENV_FILE}
  ${FRONTEND_RUNTIME_FILE}

如果要使用真实高德数据，请编辑 ${ENV_FILE}：
  AMAP_WEB_SERVICE_KEY=你的高德 Web 服务 Key
  AMAP_MOCK=false

然后执行：
  bash scripts/start.sh
EOF
}

main "$@"
