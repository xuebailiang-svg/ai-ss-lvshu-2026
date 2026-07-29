#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
[[ "${SCRIPT_DIR}" == "${BASH_SOURCE[0]}" ]] && SCRIPT_DIR="."
SOURCE_ROOT="$(cd "${SCRIPT_DIR}" && pwd)"
DEPLOY_ROOT="${ESPORTS_APP_ROOT:-/opt/esports-site-selection/app/ai-ss-lvshu-2026-main}"
APP_ROOT="${DEPLOY_ROOT}"
SERVICE_NAME="esports-site-selection"
APP_USER="esports-site-selection"
APP_GROUP="esports-site-selection"
CONFIG_DIR="/etc/esports-site-selection"
ENV_FILE="${CONFIG_DIR}/backend.env"
FRONTEND_RUNTIME_FILE="${CONFIG_DIR}/frontend-runtime.json"
DATA_DIR="/var/lib/esports-site-selection"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
NGINX_AVAILABLE="/etc/nginx/sites-available/esports-site-selection"
NGINX_ENABLED="/etc/nginx/sites-enabled/esports-site-selection"
FRONTEND_DIST_CONFIG="${APP_ROOT}/frontend/dist/config.json"
MODE="install"

if [[ "${1:-}" == "--check" ]]; then
  MODE="check"
elif [[ "${1:-}" == "--upgrade" ]]; then
  MODE="upgrade"
elif [[ "${1:-}" == "--reinstall" ]]; then
  MODE="reinstall"
elif [[ "${1:-}" != "" ]]; then
  echo "Usage: sudo ./install.sh [--check|--upgrade|--reinstall]" >&2
  exit 2
fi

if [[ "${EUID}" -eq 0 ]]; then
  SUDO=()
else
  SUDO=(sudo)
fi

log() { echo "==> $*"; }
warn() { echo "WARNING: $*" >&2; }
fail() { echo "ERROR: $*" >&2; exit 1; }

copy_source_to_deploy_root() {
  [[ "${MODE}" != "check" ]] || return 0
  [[ "${SOURCE_ROOT}" != "${DEPLOY_ROOT}" ]] || return 0

  log "同步应用代码到固定部署目录：${DEPLOY_ROOT}"
  install -d -m 0755 -o root -g root "$(dirname "${DEPLOY_ROOT}")"

  local staging
  staging="$(mktemp -d /tmp/esports-site-selection-deploy.XXXXXX)"
  tar -C "${SOURCE_ROOT}" \
    --exclude='./.git' \
    --exclude='./backend/.venv' \
    --exclude='./crawler/.venv' \
    --exclude='./crawler/offline-bundle' \
    --exclude='./crawler/*.tar.gz' \
    --exclude='./frontend/node_modules' \
    --exclude='./frontend/dist' \
    --exclude='./backups' \
    --exclude='./*.zip' \
    -cf - . | tar -C "${staging}" -xf -

  rm -rf "${DEPLOY_ROOT}"
  install -d -m 0755 -o root -g root "${DEPLOY_ROOT}"
  tar -C "${staging}" -cf - . | tar -C "${DEPLOY_ROOT}" -xf -
  rm -rf "${staging}"
  chmod +x "${DEPLOY_ROOT}/install.sh" 2>/dev/null || true

  log "切换到固定部署目录继续安装"
  exec bash "${DEPLOY_ROOT}/install.sh" "${1:-}"
}

require_root_for_write() {
  if [[ "${MODE}" != "check" && "${EUID}" -ne 0 ]]; then
    fail "install/upgrade requires root. Run: sudo ./install.sh or sudo ./install.sh --upgrade"
  fi
}

need_command() {
  command -v "$1" >/dev/null 2>&1 || return 1
}

apt_install_if_missing() {
  local missing=()
  need_command python3 || missing+=(python3 python3-venv python3-pip)
  need_command curl || missing+=(curl)
  need_command nginx || missing+=(nginx)
  need_command psql || missing+=(postgresql postgresql-contrib postgis)
  need_command node || missing+=(nodejs)
  need_command npm || missing+=(npm)

  if [[ "${#missing[@]}" -eq 0 ]]; then
    return 0
  fi
  if [[ "${MODE}" == "check" ]]; then
    warn "缺少命令或软件包：${missing[*]}"
    return 0
  fi
  log "安装系统依赖：${missing[*]}"
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y "${missing[@]}"
}

read_secret() {
  local prompt="$1"
  local value
  read -r -s -p "${prompt}" value
  echo >&2
  printf '%s' "${value}"
}

generate_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "${1:-32}"
  else
    python3 -c "import secrets; print(secrets.token_hex(${1:-32}))"
  fi
}

read_text_default_no() {
  local prompt="$1"
  local value
  read -r -p "${prompt} [y/N]: " value || true
  [[ "${value}" == "y" || "${value}" == "Y" ]]
}

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read())[1:-1])'
}

extract_database_password() {
  python3 - "${ENV_FILE}" <<'PY' 2>/dev/null || true
import os, sys
from urllib.parse import urlparse, unquote
path = sys.argv[1]
if not os.path.exists(path):
    sys.exit(0)
for line in open(path, encoding="utf-8"):
    if line.startswith("DATABASE_URL="):
        parsed = urlparse(line.split("=", 1)[1].strip())
        if parsed.password:
            print(unquote(parsed.password))
        break
PY
}

ensure_user_and_dirs() {
  log "创建运行用户和目录"
  if ! id "${APP_USER}" >/dev/null 2>&1; then
    useradd --system --home "${DATA_DIR}" --shell /usr/sbin/nologin "${APP_USER}"
  fi
  install -d -m 0755 -o root -g root "${CONFIG_DIR}"
  install -d -m 0755 -o "${APP_USER}" -g "${APP_GROUP}" "${DATA_DIR}"
  chown "${APP_USER}:${APP_GROUP}" "${DATA_DIR}"
  chmod 0755 "${DATA_DIR}"

  for file in site_feedback.json agent_traces.json; do
    if [[ ! -f "${DATA_DIR}/${file}" ]]; then
      if [[ "${file}" == "site_feedback.json" ]]; then
        printf '{"events":[]}\n' >"${DATA_DIR}/${file}"
      else
        printf '{"traces":{}}\n' >"${DATA_DIR}/${file}"
      fi
    fi
    chown "${APP_USER}:${APP_GROUP}" "${DATA_DIR}/${file}"
    chmod 0640 "${DATA_DIR}/${file}"
  done
}

write_backend_env() {
  local db_password="$1"
  local amap_key="$2"
  local db_password_url
  db_password_url="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "${db_password}")"
  local tmp
  local encryption_key admin_token
  encryption_key="$(generate_secret 32)"
  admin_token="$(generate_secret 24)"
  tmp="$(mktemp)"
  cat >"${tmp}" <<EOF
APP_ENV=production
DATABASE_URL=postgresql+psycopg://site_selection:${db_password_url}@127.0.0.1:5432/site_selection
AMAP_WEB_SERVICE_KEY=${amap_key}
AMAP_MOCK=false
SCORING_CONFIG_PATH=app/scoring/default.yaml
ENABLE_TRACE=true
ENABLE_FEEDBACK=true
ENABLE_REFLECTION=true
ENABLE_SIMILAR_CASES=true
ENABLE_DEBUG_API=false
ENABLE_DEBUG_ENDPOINTS=false
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
CRAWLER_ENABLED=false
CRAWLER_PROVIDER=crawl4ai
CRAWLER_TIMEOUT_SECONDS=60
CRAWLER_MAX_PAGES_PER_TASK=5
CRAWLER_MAX_TASKS_PER_PROJECT=50
CRAWLER_RATE_LIMIT_SECONDS=5
CRAWLER_ALLOWED_DOMAINS=
CRAWLER_BLOCKED_DOMAINS=
CRAWLER_SEARCH_ENABLED=true
CRAWLER_SEARCH_PROVIDER=bing_html
CRAWLER_SEARCH_MAX_RESULTS=5
CRAWLER_SEARCH_TIMEOUT_SECONDS=10
CRAWLER_SEARCH_ALLOWED_DOMAINS=
GOV_DATA_ENABLED=true
GOV_DATA_SOURCES=national,shaanxi,xian
GOV_DATA_TIMEOUT_SECONDS=15
GOV_DATA_MAX_RETRIES=2
GOV_DATA_RATE_LIMIT_SECONDS=1
GOV_DATA_USER_AGENT="esports-site-selection/1.0 (+government-public-data)"
SYSTEM_CONFIG_ENCRYPTION_KEY=${encryption_key}
ADMIN_CONFIG_TOKEN=${admin_token}
SITE_FEEDBACK_STORE_PATH=/var/lib/esports-site-selection/site_feedback.json
AGENT_TRACE_STORE_PATH=/var/lib/esports-site-selection/agent_traces.json
EOF
  install -m 0640 -o root -g "${APP_GROUP}" "${tmp}" "${ENV_FILE}"
  rm -f "${tmp}"
}

ensure_backend_env() {
  log "检查 backend.env"
  if [[ -s "${ENV_FILE}" ]]; then
    echo "OK: 保留已有 ${ENV_FILE}"
    return 0
  fi
  local db_password amap_key
  db_password="$(generate_secret 24)"
  amap_key=""
  write_backend_env "${db_password}" "${amap_key}"
  echo "OK: 已自动生成 ${ENV_FILE}（数据库密码、配置加密密钥和管理员 Token 均为随机强值）"
}

ensure_security_settings() {
  local changed=false value
  for key in SYSTEM_CONFIG_ENCRYPTION_KEY ADMIN_CONFIG_TOKEN; do
    if ! grep -Eq "^${key}=.{16,}$" "${ENV_FILE}"; then
      value="$(generate_secret 32)"
      if grep -q "^${key}=" "${ENV_FILE}"; then
        sed -i "s|^${key}=.*|${key}=${value}|" "${ENV_FILE}"
      else
        printf '%s=%s\n' "${key}" "${value}" >>"${ENV_FILE}"
      fi
      changed=true
    fi
  done
  chown root:"${APP_GROUP}" "${ENV_FILE}"
  chmod 0640 "${ENV_FILE}"
  if [[ "${changed}" == true ]]; then
    echo "OK: 已补充配置中心安全密钥（未打印完整值）"
  fi
}

ensure_crawler_settings() {
  local changed=false
  declare -A defaults=(
    [CRAWLER_ENABLED]=false
    [CRAWLER_PROVIDER]=crawl4ai
    [CRAWLER_TIMEOUT_SECONDS]=60
    [CRAWLER_MAX_PAGES_PER_TASK]=5
    [CRAWLER_MAX_TASKS_PER_PROJECT]=50
    [CRAWLER_RATE_LIMIT_SECONDS]=5
    [CRAWLER_ALLOWED_DOMAINS]=
    [CRAWLER_BLOCKED_DOMAINS]=
    [CRAWLER_SEARCH_ENABLED]=true
    [CRAWLER_SEARCH_PROVIDER]=bing_html
    [CRAWLER_SEARCH_MAX_RESULTS]=5
    [CRAWLER_SEARCH_TIMEOUT_SECONDS]=10
    [CRAWLER_SEARCH_ALLOWED_DOMAINS]=
  )

  for key in "${!defaults[@]}"; do
    if ! grep -q "^${key}=" "${ENV_FILE}"; then
      printf '%s=%s\n' "${key}" "${defaults[$key]}" >>"${ENV_FILE}"
      changed=true
    fi
  done

  if grep -q '^CRAWLER_SEARCH_PROVIDER=duckduckgo_html$' "${ENV_FILE}"; then
    sed -i 's|^CRAWLER_SEARCH_PROVIDER=duckduckgo_html$|CRAWLER_SEARCH_PROVIDER=bing_html|' "${ENV_FILE}"
    changed=true
  fi

  chown root:"${APP_GROUP}" "${ENV_FILE}"
  chmod 0640 "${ENV_FILE}"
  if [[ "${changed}" == true ]]; then
    echo "OK: 已补齐爬虫配置项（保留已有 Key 和数据库配置）"
  fi
}

ensure_government_data_settings() {
  local changed=false
  declare -A defaults=(
    [GOV_DATA_ENABLED]=true
    [GOV_DATA_SOURCES]=national,shaanxi,xian
    [GOV_DATA_TIMEOUT_SECONDS]=15
    [GOV_DATA_MAX_RETRIES]=2
    [GOV_DATA_RATE_LIMIT_SECONDS]=1
    [GOV_DATA_USER_AGENT]="esports-site-selection/1.0 (+government-public-data)"
  )

  for key in "${!defaults[@]}"; do
    if ! grep -q "^${key}=" "${ENV_FILE}"; then
      if [[ "${key}" == "GOV_DATA_USER_AGENT" ]]; then
        printf '%s="%s"\n' "${key}" "${defaults[$key]}" >>"${ENV_FILE}"
      else
        printf '%s=%s\n' "${key}" "${defaults[$key]}" >>"${ENV_FILE}"
      fi
      changed=true
    fi
  done

  if grep -Fxq 'GOV_DATA_USER_AGENT=esports-site-selection/1.0 (+government-public-data)' "${ENV_FILE}"; then
    sed -i 's|^GOV_DATA_USER_AGENT=esports-site-selection/1.0 (+government-public-data)$|GOV_DATA_USER_AGENT="esports-site-selection/1.0 (+government-public-data)"|' "${ENV_FILE}"
    changed=true
  fi

  chown root:"${APP_GROUP}" "${ENV_FILE}"
  chmod 0640 "${ENV_FILE}"
  if [[ "${changed}" == true ]]; then
    echo "OK: 已补齐政府公开数据配置项"
  fi
}

normalize_frontend_runtime_config() {
  install -d -m 0755 -o root -g root "${CONFIG_DIR}"
  local js_key="" security="" tmp
  if [[ -s "${FRONTEND_RUNTIME_FILE}" ]]; then
    js_key="$(python3 - "${FRONTEND_RUNTIME_FILE}" <<'PY' 2>/dev/null || true
import json, sys
try:
    print((json.load(open(sys.argv[1], encoding="utf-8")) or {}).get("amapJsKey") or "")
except Exception:
    pass
PY
)"
    security="$(python3 - "${FRONTEND_RUNTIME_FILE}" <<'PY' 2>/dev/null || true
import json, sys
try:
    print((json.load(open(sys.argv[1], encoding="utf-8")) or {}).get("amapSecurityJsCode") or "")
except Exception:
    pass
PY
)"
  fi
  tmp="$(mktemp)"
  python3 - "${tmp}" "${js_key}" "${security}" <<'PY'
import json, sys
path, key, security = sys.argv[1:4]
data = {
    "apiBaseUrl": "/api",
    "amapJsKey": key,
    "amapSecurityJsCode": security,
    "mapProvider": "amap",
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")
PY
  install -m 0644 -o root -g root "${tmp}" "${FRONTEND_RUNTIME_FILE}"
  rm -f "${tmp}"
  chmod 0755 "${CONFIG_DIR}"
  chmod 0644 "${FRONTEND_RUNTIME_FILE}"
  if [[ -z "${js_key}" ]]; then
    warn "${FRONTEND_RUNTIME_FILE} 未配置 amapJsKey，公网地图会显示 Key 未配置提示。"
  else
    echo "OK: 前端 runtime 配置已保留/写入 amapJsKey（未打印完整 Key）"
  fi
}

prepare_reinstall() {
  [[ "${MODE}" == "reinstall" ]] || return 0
  log "重建应用运行环境（保留配置、数据库和生产数据）"
  systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
  rm -rf "${APP_ROOT}/backend/.venv" "${APP_ROOT}/frontend/dist"
}

ensure_postgres() {
  log "检查 PostgreSQL / PostGIS"
  systemctl enable --now postgresql
  systemctl is-active --quiet postgresql || fail "postgresql 未运行"

  local db_password
  db_password="$(extract_database_password)"
  if [[ -z "${db_password}" ]]; then
    db_password="$(read_secret "请输入 PostgreSQL 密码 site_selection: ")"
  fi
  [[ -n "${db_password}" ]] || fail "无法获取 site_selection 数据库密码"

  local role_exists db_exists
  role_exists="$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='site_selection';" | tr -d '[:space:]')"
  if [[ "${role_exists}" != "1" ]]; then
    sudo -u postgres psql -v pw="${db_password}" -c "CREATE USER site_selection WITH PASSWORD :'pw';"
  elif [[ "${MODE}" == "install" ]] && read_text_default_no "数据库用户 site_selection 已存在，是否更新密码"; then
    sudo -u postgres psql -v pw="${db_password}" -c "ALTER USER site_selection WITH PASSWORD :'pw';"
  fi

  db_exists="$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='site_selection';" | tr -d '[:space:]')"
  if [[ "${db_exists}" != "1" ]]; then
    sudo -u postgres createdb -O site_selection site_selection
  fi
  sudo -u postgres psql -d site_selection -c "CREATE EXTENSION IF NOT EXISTS postgis;"
}

install_backend() {
  log "安装后端依赖并迁移数据库"
  python3 -m venv "${APP_ROOT}/backend/.venv"
  "${APP_ROOT}/backend/.venv/bin/python" -m pip install --upgrade pip
  # 爬虫拥有独立虚拟环境。清理旧版本曾装入主后端环境的浏览器依赖，
  # 避免升级后误以为主服务仍承担爬虫执行。
  "${APP_ROOT}/backend/.venv/bin/pip" uninstall -y crawl4ai playwright >/dev/null 2>&1 || true
  "${APP_ROOT}/backend/.venv/bin/pip" install -r "${APP_ROOT}/backend/requirements.txt"
  "${APP_ROOT}/backend/.venv/bin/pip" install -e "${APP_ROOT}/backend"
  runuser -u "${APP_USER}" -- bash -c "set -a; source '${ENV_FILE}'; set +a; cd '${APP_ROOT}/backend'; .venv/bin/alembic upgrade head"
}

backup_before_migration() {
  log "迁移前自动备份数据库"
  BACKUP_DIR="${APP_ROOT}/backups" BACKEND_ENV_FILE="${ENV_FILE}" bash "${APP_ROOT}/scripts/backup-db.sh"
}

install_frontend() {
  log "安装前端依赖并构建"
  npm --prefix "${APP_ROOT}/frontend" install --no-audit --no-fund
  npm --prefix "${APP_ROOT}/frontend" run build
  test -s "${APP_ROOT}/frontend/dist/index.html" || fail "frontend/dist/index.html 不存在，前端构建失败"
  mkdir -p "${APP_ROOT}/frontend/dist"
  printf '{"apiBaseUrl":"/api"}\n' >"${FRONTEND_DIST_CONFIG}"
  chmod 0644 "${FRONTEND_DIST_CONFIG}"
}

write_systemd() {
  log "生成 systemd service"
  cat >"${SERVICE_FILE}" <<EOF
[Unit]
Description=Esports Site Selection FastAPI Service
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=simple
User=esports-site-selection
Group=esports-site-selection
WorkingDirectory=${APP_ROOT}/backend
EnvironmentFile=/etc/esports-site-selection/backend.env
Environment=PYTHONUNBUFFERED=1
Environment=SITE_FEEDBACK_STORE_PATH=/var/lib/esports-site-selection/site_feedback.json
Environment=AGENT_TRACE_STORE_PATH=/var/lib/esports-site-selection/agent_traces.json
ExecStart=${APP_ROOT}/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/var/lib/esports-site-selection

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable "${SERVICE_NAME}"
  systemctl restart "${SERVICE_NAME}"
  if systemctl cat esports-site-selection-crawler.service >/dev/null 2>&1; then
    if grep -q 'ExecStart=.*/crawler/.venv/bin/python' /etc/systemd/system/esports-site-selection-crawler.service 2>/dev/null; then
      log "重启已安装的独立爬虫 Worker 以加载新代码"
      systemctl restart esports-site-selection-crawler.service || warn "独立爬虫 Worker 重启失败，不影响主系统；请查看其日志"
    else
      systemctl disable --now esports-site-selection-crawler.service 2>/dev/null || true
      warn "检测到旧版内置爬虫服务，已停止。请单独执行 scripts/crawler/install.sh 完成迁移"
    fi
  fi
}

write_nginx() {
  log "生成 Nginx 配置"
  cat >"${NGINX_AVAILABLE}" <<EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    root ${APP_ROOT}/frontend/dist;
    index index.html;
    client_max_body_size 2m;
    gzip on;
    gzip_comp_level 5;
    gzip_min_length 1024;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml image/svg+xml;

    location = /config.json {
        alias ${APP_ROOT}/frontend/dist/config.json;
        default_type application/json;
        add_header Cache-Control "no-store";
    }

    location = /runtime-config.json {
        alias /etc/esports-site-selection/frontend-runtime.json;
        default_type application/json;
        add_header Cache-Control "no-store";
    }

    location /assets/ {
        try_files \$uri =404;
        access_log off;
        expires 7d;
        add_header Cache-Control "public, max-age=604800, immutable";
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 10s;
        proxy_read_timeout 120s;
    }

    location = /nginx-health {
        access_log off;
        default_type text/plain;
        return 200 "ok\n";
    }

    location ~ /\.(?!well-known) {
        return 404;
    }

    location ~* /(vendor|node_modules|backend|deploy|scripts|docs|\.git)/ {
        return 404;
    }

    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
EOF
  ln -sfn "${NGINX_AVAILABLE}" "${NGINX_ENABLED}"
  rm -f /etc/nginx/sites-enabled/default
  nginx -t
  systemctl enable nginx
  systemctl reload nginx || systemctl restart nginx
}

wait_for_url() {
  local name="$1" url="$2" max="${3:-30}" i
  for i in $(seq 1 "${max}"); do
    if curl --fail --silent --show-error --max-time 5 "${url}" >/dev/null; then
      echo "OK: ${name} ready"
      return 0
    fi
    sleep 1
  done
  return 1
}

check_json_endpoint() {
  local name="$1" url="$2" result status content_type body
  result="$(curl --silent --show-error --output /tmp/esports-check-body --write-out '%{http_code} %{content_type}' --max-time 10 "${url}" 2>&1)" || fail "${name} 请求失败：${result}"
  status="${result%% *}"
  content_type="${result#* }"
  body="$(head -c 80 /tmp/esports-check-body || true)"
  rm -f /tmp/esports-check-body
  [[ "${status}" == "200" ]] || fail "${name} HTTP ${status}，期望 200"
  [[ "${content_type}" == application/json* ]] || fail "${name} Content-Type ${content_type}，期望 application/json"
  [[ "${body}" != *"<div id=\"root\""* && "${body}" != *"<script"* ]] || fail "${name} 返回了 index.html，不是 JSON"
  echo "OK: ${name} -> ${status} ${content_type}"
}

validate_asset_loading() {
  local js_path status content_type length
  js_path="$(python3 - "${APP_ROOT}/frontend/dist/index.html" <<'PY'
import re, sys
html = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r'src="([^"]*assets/[^"]+\.js)"', html)
print(m.group(1) if m else "")
PY
)"
  [[ -n "${js_path}" ]] || fail "无法从 index.html 解析 JS 资源路径"
  status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' --max-time 10 "http://127.0.0.1${js_path}")"
  content_type="$(curl --silent --show-error --output /dev/null --write-out '%{content_type}' --max-time 10 "http://127.0.0.1${js_path}")"
  length="$(curl --silent --show-error --output /dev/null --write-out '%{size_download}' --max-time 20 "http://127.0.0.1${js_path}")"
  [[ "${status}" == "200" ]] || fail "JS 资源 ${js_path} HTTP ${status}"
  [[ "${content_type}" == application/javascript* || "${content_type}" == text/javascript* ]] || fail "JS 资源 Content-Type ${content_type} 异常"
  [[ "${length}" -gt 100000 ]] || fail "JS 资源大小 ${length} 过小，可能返回了错误页面"
  echo "OK: JS asset ${js_path} -> ${status} ${content_type}, ${length} bytes"
}

assert_no_app_root_placeholder() {
  if grep -R "__APP_ROOT__" /etc/nginx "${SERVICE_FILE}" 2>/dev/null; then
    fail "发现 __APP_ROOT__ 残留，请检查 Nginx/systemd 生成逻辑"
  fi
  echo "OK: 未发现 __APP_ROOT__ 残留"
}

validate_deployment() {
  log "部署后验收"
  nginx -t
  wait_for_url "backend direct health" "http://127.0.0.1:8000/api/system/health" 30 || fail "后端直连 health 失败"
  wait_for_url "nginx health" "http://127.0.0.1/nginx-health" 30 || fail "Nginx health 失败"
  wait_for_url "nginx api health" "http://127.0.0.1/api/system/health" 30 || fail "Nginx API health 失败"
  curl --silent --show-error --head --max-time 10 http://127.0.0.1/ | grep -qi "200 OK" || fail "首页不是 200"
  validate_asset_loading
  check_json_endpoint "frontend config" "http://127.0.0.1/config.json"
  check_json_endpoint "frontend runtime config" "http://127.0.0.1/runtime-config.json"
  python3 - <<'PY'
import json, urllib.request, sys
for url in ("http://127.0.0.1/api/system/health", "http://127.0.0.1:8000/api/system/health"):
    data = json.load(urllib.request.urlopen(url, timeout=10))
    if data.get("status") not in {"ok", "warning"}:
        raise SystemExit(f"health failed: {url} -> {data}")
    warnings = data.get("warnings") or []
    if warnings:
        print(f"WARNING: {url} 服务正常，但仍有待配置项：{warnings}")
    else:
        print(f"OK: {url} health status=ok warnings=[]")
PY
  assert_no_app_root_placeholder
}

run_check() {
  echo "SOURCE_ROOT=${SOURCE_ROOT}"
  echo "DEPLOY_ROOT=${DEPLOY_ROOT}"
  echo "APP_ROOT=${APP_ROOT}"
  for cmd in python3 node npm psql nginx curl systemctl ss; do
    if need_command "${cmd}"; then echo "OK: ${cmd}"; else warn "缺少 ${cmd}"; fi
  done
  for port in 80 8000 5432; do
    if ss -ltn "( sport = :${port} )" 2>/dev/null | grep -q ":${port}"; then
      echo "INFO: port ${port} is listening"
    else
      echo "INFO: port ${port} is not listening"
    fi
  done
  [[ -f "${ENV_FILE}" ]] && echo "OK: ${ENV_FILE}" || warn "缺少 ${ENV_FILE}"
  [[ -f "${FRONTEND_RUNTIME_FILE}" ]] && echo "OK: ${FRONTEND_RUNTIME_FILE}" || warn "缺少 ${FRONTEND_RUNTIME_FILE}"
  grep -R "__APP_ROOT__" /etc/nginx "${SERVICE_FILE}" 2>/dev/null || true
  curl --silent --show-error --max-time 5 http://127.0.0.1/api/system/health || true
  echo
}

main() {
  if [[ "${MODE}" == "check" ]]; then
    run_check
    return 0
  fi
  require_root_for_write
  copy_source_to_deploy_root "${1:-}"
  apt_install_if_missing
  prepare_reinstall
  ensure_user_and_dirs
  ensure_backend_env
  ensure_security_settings
  ensure_crawler_settings
  ensure_government_data_settings
  normalize_frontend_runtime_config
  ensure_postgres
  backup_before_migration
  install_backend
  install_frontend
  write_systemd
  write_nginx
  validate_deployment
  cat <<EOF

部署完成。

Frontend:
  http://服务器公网IP/

Health:
  curl http://127.0.0.1/api/system/health

配置文件:
  ${ENV_FILE}
  ${FRONTEND_RUNTIME_FILE}

生产数据:
  ${DATA_DIR}/site_feedback.json
  ${DATA_DIR}/agent_traces.json

独立爬虫（可选，主系统部署不会下载浏览器）:
  sudo bash ${APP_ROOT}/scripts/crawler/install.sh

日常升级:
  sudo ./install.sh --upgrade

保留数据重装:
  sudo ./install.sh --reinstall

查看 Web 配置中心管理员 Token（请勿复制到日志或聊天）:
  sudo grep '^ADMIN_CONFIG_TOKEN=' ${ENV_FILE}
EOF
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
