#!/usr/bin/env bash
set -Eeuo pipefail

BASE_URL="${APP_BASE_URL:-http://127.0.0.1}"
BACKEND_URL="${BACKEND_BASE_URL:-http://127.0.0.1:8000}"
PROJECT_ID=""
CHECK_MIGRATION=true

usage() {
  cat <<'EOF'
用法：
  bash scripts/acceptance-mvp.sh [--project-id proj_xxx] [--base-url URL] [--backend-url URL] [--skip-migration]

说明：
  - 默认执行只读发布前检查，不创建项目、不采集数据、不调用 AI。
  - 传入 project-id 后，额外核对项目、数据集和数据准备度。
  - 脚本不会打印 API Key、Token、DATABASE_URL 或数据库密码。
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-id) PROJECT_ID="${2:-}"; shift 2 ;;
    --base-url) BASE_URL="${2:-}"; shift 2 ;;
    --backend-url) BACKEND_URL="${2:-}"; shift 2 ;;
    --skip-migration) CHECK_MIGRATION=false; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: 未知参数 $1" >&2; usage >&2; exit 2 ;;
  esac
done

BASE_URL="${BASE_URL%/}"
BACKEND_URL="${BACKEND_URL%/}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

pass_count=0
fail_count=0

ok() { echo "OK: $*"; pass_count=$((pass_count + 1)); }
bad() { echo "ERROR: $*" >&2; fail_count=$((fail_count + 1)); }

require_command() {
  if command -v "$1" >/dev/null 2>&1; then ok "命令可用：$1"; else bad "缺少命令：$1"; fi
}

fetch_json() {
  local label="$1" url="$2" output="$3"
  local meta status content_type
  if ! meta="$(curl --silent --show-error --location --output "${output}" --write-out '%{http_code} %{content_type}' --max-time 20 "${url}" 2>&1)"; then
    bad "${label} 请求失败：${meta}"
    return 1
  fi
  status="${meta%% *}"
  content_type="${meta#* }"
  if [[ "${status}" != "200" || "${content_type}" != application/json* ]]; then
    bad "${label} 返回 HTTP ${status}, Content-Type ${content_type}"
    return 1
  fi
  if ! python3 -m json.tool "${output}" >/dev/null 2>&1; then
    bad "${label} 返回内容不是有效 JSON"
    return 1
  fi
  ok "${label}"
}

check_page() {
  local label="$1" url="$2"
  local meta status content_type
  if ! meta="$(curl --silent --show-error --location --output /dev/null --write-out '%{http_code} %{content_type}' --max-time 20 "${url}" 2>&1)"; then
    bad "${label} 请求失败：${meta}"
    return
  fi
  status="${meta%% *}"
  content_type="${meta#* }"
  if [[ "${status}" == "200" && "${content_type}" == text/html* ]]; then ok "${label}"; else bad "${label} 返回 HTTP ${status}, Content-Type ${content_type}"; fi
}

echo "电竞馆智能选址 MVP 发布前验收"
echo "Frontend: ${BASE_URL}"
echo "Backend:  ${BACKEND_URL}"
[[ -n "${PROJECT_ID}" ]] && echo "Project:  ${PROJECT_ID}"
echo

require_command curl
require_command python3

fetch_json "后端健康检查" "${BACKEND_URL}/api/system/health" "${TMP_DIR}/backend-health.json" || true
fetch_json "Nginx API 健康检查" "${BASE_URL}/api/system/health" "${TMP_DIR}/proxy-health.json" || true
fetch_json "系统配置状态" "${BASE_URL}/api/system/config-status" "${TMP_DIR}/config-status.json" || true
fetch_json "数据源状态" "${BASE_URL}/api/data-sources/status" "${TMP_DIR}/data-sources.json" || true
fetch_json "项目列表 API" "${BASE_URL}/api/projects" "${TMP_DIR}/projects.json" || true
check_page "项目列表页面" "${BASE_URL}/"
check_page "系统配置页面" "${BASE_URL}/settings"

if [[ -f "${TMP_DIR}/config-status.json" ]]; then
  if python3 - "${TMP_DIR}/config-status.json" <<'PY'
import json, re, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
text = json.dumps(data, ensure_ascii=False)
patterns = [r"sk-[A-Za-z0-9_-]{20,}", r"ADMIN_CONFIG_TOKEN", r"SYSTEM_CONFIG_ENCRYPTION_KEY", r"encrypted_value"]
raise SystemExit(1 if any(re.search(pattern, text) for pattern in patterns) else 0)
PY
  then ok "公开配置响应未泄露完整 Key/Token"; else bad "公开配置响应疑似包含敏感信息"; fi
fi

if [[ -n "${PROJECT_ID}" ]]; then
  fetch_json "项目详情" "${BASE_URL}/api/projects/${PROJECT_ID}" "${TMP_DIR}/project.json" || true
  fetch_json "项目统一数据集" "${BASE_URL}/api/projects/${PROJECT_ID}/dataset" "${TMP_DIR}/dataset.json" || true
  fetch_json "项目数据准备度" "${BASE_URL}/api/projects/${PROJECT_ID}/data-quality" "${TMP_DIR}/quality.json" || true
  check_page "项目工作台页面" "${BASE_URL}/projects/${PROJECT_ID}"
  check_page "人工核实页面" "${BASE_URL}/projects/${PROJECT_ID}/supplement"

  if [[ -f "${TMP_DIR}/project.json" && -f "${TMP_DIR}/dataset.json" ]]; then
    if python3 - "${TMP_DIR}/project.json" "${TMP_DIR}/dataset.json" <<'PY'
import json, sys
project_payload = json.load(open(sys.argv[1], encoding="utf-8"))
dataset = json.load(open(sys.argv[2], encoding="utf-8"))
stats = project_payload.get("stats") or {}
pois = dataset.get("pois") or []
if int(stats.get("poi_count") or 0) != len(pois):
    print(f"项目统计 poi_count={stats.get('poi_count')}，数据集 pois={len(pois)}", file=sys.stderr)
    raise SystemExit(1)
identifiers = []
for item in pois:
    identifiers.append(item.get("amap_poi_id") or item.get("source_id") or item.get("id"))
identifiers = [str(value) for value in identifiers if value is not None]
if len(identifiers) != len(set(identifiers)):
    print("项目数据集中存在重复 POI 标识", file=sys.stderr)
    raise SystemExit(1)
PY
    then ok "页面项目统计与统一数据集 POI 数量一致且标识唯一"; else bad "项目统计/数据集一致性检查失败"; fi
  fi

  if [[ -f "${TMP_DIR}/quality.json" ]]; then
    if python3 - "${TMP_DIR}/quality.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
readiness = data.get("readiness") or {}
groups = readiness.get("groups") or {}
required = {"technical_prerequisites", "key_unknowns", "recommended", "optional"}
if not required.issubset(groups):
    print("readiness.groups 缺少固定业务分组", file=sys.stderr)
    raise SystemExit(1)
if "quality_score" not in data:
    print("缺少 quality_score", file=sys.stderr)
    raise SystemExit(1)
PY
    then ok "数据准备度包含固定四类检查项"; else bad "数据准备度契约检查失败"; fi
  fi
fi

if [[ "${CHECK_MIGRATION}" == true ]]; then
  VENV_ALEMBIC="${ROOT_DIR}/backend/.venv/bin/alembic"
  ENV_FILE="/etc/esports-site-selection/backend.env"
  if [[ -x "${VENV_ALEMBIC}" && -f "${ENV_FILE}" ]]; then
    if migration_output="$(set -a; source "${ENV_FILE}"; set +a; cd "${ROOT_DIR}/backend"; current_output="$("${VENV_ALEMBIC}" current 2>&1)"; heads_output="$("${VENV_ALEMBIC}" heads 2>&1)"; printf '%s\n---HEADS---\n%s\n' "${current_output}" "${heads_output}")"; then
      current_revision="$(sed -n '/---HEADS---/q; /^[0-9][A-Za-z0-9_]* /{s/ .*//;p;}' <<<"${migration_output}" | tail -n 1)"
      head_revisions="$(sed -n '/---HEADS---/,$p' <<<"${migration_output}" | sed -n '/^[0-9][A-Za-z0-9_]* (head)$/{s/ .*//;p;}')"
      head_count="$(grep -c . <<<"${head_revisions}" || true)"
      head_revision="$(head -n 1 <<<"${head_revisions}")"
      if [[ "${head_count}" == "1" && -n "${current_revision}" && "${current_revision}" == "${head_revision}" ]]; then
        ok "Alembic current 与唯一 head 一致"
      else
        bad "Alembic 未处于唯一 head，请手工执行 alembic current/heads"
      fi
    else
      bad "Alembic 检查失败（未输出 DATABASE_URL）"
    fi
  else
    echo "SKIP: 当前目录不是已安装的 Ubuntu 运行目录，未执行 Alembic 检查"
  fi
fi

echo
echo "Summary: ${pass_count} passed, ${fail_count} failed"
if (( fail_count > 0 )); then
  echo "请按 docs/ACCEPTANCE_AMAP_MANUAL_AI_MVP.md 记录失败项，修复后重新执行。" >&2
  exit 1
fi
echo "自动检查通过；仍需在浏览器完成地址确认、人工核实、AI 提问、报告数字追溯和打印视觉验收。"
