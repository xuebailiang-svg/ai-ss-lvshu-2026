#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_DIR=/etc/esports-site-selection
BACKEND_ENV="${ENV_DIR}/backend.env"
FRONTEND_ENV="${APP_ROOT}/frontend/.env.production"
APP_GROUP=esports-site-selection

if [[ "${EUID}" -eq 0 ]]; then
  SUDO=()
else
  SUDO=(sudo)
fi

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

mask_secret() {
  local value="${1:-}"
  local len=${#value}
  if [[ -z "${value}" ]]; then
    echo "missing"
  elif (( len <= 8 )); then
    echo "***"
  else
    echo "${value:0:4}***${value: -4}"
  fi
}

quote_env() {
  local value="${1:-}"
  value="${value//\'/\'\\\'\'}"
  printf "'%s'" "${value}"
}

get_existing() {
  local name="$1"
  if "${SUDO[@]}" test -r "${BACKEND_ENV}" 2>/dev/null; then
    "${SUDO[@]}" bash -c "set -a; source '${BACKEND_ENV}' 2>/dev/null; set +a; printf '%s' \"\${${name}:-}\""
  fi
}

prompt_secret() {
  local label="$1"
  local current="$2"
  local value
  if [[ -n "${current}" ]]; then
    echo "${label} 当前值：$(mask_secret "${current}")"
    read -rsp "请输入新的 ${label}，直接回车保留当前值：" value
  else
    read -rsp "请输入 ${label}，直接回车留空：" value
  fi
  echo
  if [[ -z "${value}" ]]; then
    printf '%s' "${current}"
  else
    printf '%s' "${value}"
  fi
}

prompt_visible() {
  local label="$1"
  local current="$2"
  local value
  if [[ -n "${current}" ]]; then
    read -rp "请输入 ${label}，直接回车保留当前值 [${current}]：" value
  else
    read -rp "请输入 ${label}：" value
  fi
  printf '%s' "${value:-${current}}"
}

command -v "${SUDO[0]:-true}" >/dev/null 2>&1 || fail "需要 root 或 sudo。"
id "${APP_GROUP}" >/dev/null 2>&1 || true
getent group "${APP_GROUP}" >/dev/null 2>&1 || fail "缺少 ${APP_GROUP} 组，请先运行 scripts/bootstrap-ubuntu-direct.sh。"

"${SUDO[@]}" install -d -m 0750 -o root -g "${APP_GROUP}" "${ENV_DIR}"

existing_app_env="$(get_existing APP_ENV || true)"
existing_database_url="$(get_existing DATABASE_URL || true)"
existing_amap_key="$(get_existing AMAP_WEB_SERVICE_KEY || true)"
existing_amap_mock="$(get_existing AMAP_MOCK || true)"
existing_scoring_path="$(get_existing SCORING_CONFIG_PATH || true)"
existing_debug="$(get_existing ENABLE_DEBUG_ENDPOINTS || true)"

echo "将安全写入后端配置：${BACKEND_ENV}"
echo "将写入前端构建配置：${FRONTEND_ENV}"
echo "注意：输入内容不会回显，脚本不会打印完整 Key。"
echo

app_env="$(prompt_visible "APP_ENV" "${existing_app_env:-production}")"
database_url="$(prompt_secret "DATABASE_URL" "${existing_database_url}")"
amap_key="$(prompt_secret "高德 Web 服务 Key AMAP_WEB_SERVICE_KEY" "${existing_amap_key}")"
amap_mock="$(prompt_visible "AMAP_MOCK(true/false)" "${existing_amap_mock:-false}")"
scoring_path="$(prompt_visible "SCORING_CONFIG_PATH" "${existing_scoring_path:-app/scoring/default.yaml}")"
debug_enabled="$(prompt_visible "ENABLE_DEBUG_ENDPOINTS(true/false)" "${existing_debug:-false}")"

echo
echo "M1 当前报告为规则评分报告，不调用大模型。"
echo "因此本脚本不会收集 OPENAI_API_KEY、DEEPSEEK_API_KEY 或 LLM_API_KEY。"
echo

js_key="$(prompt_secret "高德 JavaScript API Key VITE_AMAP_JS_KEY" "")"
js_security="$(prompt_secret "高德 JS 安全密钥 VITE_AMAP_SECURITY_JS_CODE" "")"

backend_tmp="$(mktemp)"
frontend_tmp="$(mktemp)"
trap 'rm -f "${backend_tmp}" "${frontend_tmp}"' EXIT

cat >"${backend_tmp}" <<EOF
APP_ENV=$(quote_env "${app_env:-production}")
DATABASE_URL=$(quote_env "${database_url}")
AMAP_WEB_SERVICE_KEY=$(quote_env "${amap_key}")
AMAP_MOCK=$(quote_env "${amap_mock:-false}")
SCORING_CONFIG_PATH=$(quote_env "${scoring_path:-app/scoring/default.yaml}")
ENABLE_DEBUG_ENDPOINTS=$(quote_env "${debug_enabled:-false}")
EOF

cat >"${frontend_tmp}" <<EOF
VITE_AMAP_JS_KEY=${js_key}
VITE_AMAP_SECURITY_JS_CODE=${js_security}
EOF

"${SUDO[@]}" install -m 0640 -o root -g "${APP_GROUP}" "${backend_tmp}" "${BACKEND_ENV}"
install -m 0600 "${frontend_tmp}" "${FRONTEND_ENV}"

echo
echo "配置已写入。摘要："
echo "  APP_ENV=${app_env:-production}"
echo "  DATABASE_URL=$(mask_secret "${database_url}")"
echo "  AMAP_WEB_SERVICE_KEY=$(mask_secret "${amap_key}")"
echo "  AMAP_MOCK=${amap_mock:-false}"
echo "  ENABLE_DEBUG_ENDPOINTS=${debug_enabled:-false}"
echo "  VITE_AMAP_JS_KEY=$(mask_secret "${js_key}")"
echo "  VITE_AMAP_SECURITY_JS_CODE=$(mask_secret "${js_security}")"
echo
echo "如果修改了 VITE_ 前端变量，必须重新执行："
echo "  bash scripts/deploy.sh"
echo "或至少执行："
echo "  cd frontend && npm run build"
