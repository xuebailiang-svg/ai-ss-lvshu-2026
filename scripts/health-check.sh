#!/usr/bin/env bash
set -Eeuo pipefail

BASE_URL="${APP_BASE_URL:-http://127.0.0.1}"
BACKEND_URL="${BACKEND_BASE_URL:-http://127.0.0.1:8000}"
SERVICE_NAME="${SERVICE_NAME:-esports-site-selection}"

if [[ "${EUID}" -eq 0 ]]; then
  SUDO=()
else
  SUDO=(sudo)
fi

pass_count=0
fail_count=0

ok() {
  echo "OK: $*"
  pass_count=$((pass_count + 1))
}

bad() {
  echo "ERROR: $*" >&2
  fail_count=$((fail_count + 1))
}

check_command() {
  local name="$1"
  shift
  local output
  if output="$("$@" 2>&1)"; then
    ok "${name}"
  else
    bad "${name}"
    if [[ -n "${output}" ]]; then
      while IFS= read -r line; do
        echo "  ${line}" >&2
      done <<<"${output}"
    fi
  fi
}

check_json_endpoint() {
  local name="$1"
  local url="$2"
  local result
  if ! result="$(curl --silent --show-error --output /dev/null --write-out '%{http_code} %{content_type}' --max-time 8 "${url}" 2>&1)"; then
    bad "${name}"
    echo "  ${result}" >&2
    return
  fi
  local status="${result%% *}"
  local content_type="${result#* }"
  if [[ "${status}" == "200" && "${content_type}" == application/json* ]]; then
    ok "${name}"
  else
    bad "${name}: got HTTP ${status}, Content-Type ${content_type}; expected 200 application/json"
  fi
}

check_asset_endpoint() {
  local name="$1"
  local index_url="$2"
  local asset_path
  asset_path="$(curl --silent --show-error --max-time 8 "${index_url}" | python3 -c 'import re,sys; html=sys.stdin.read(); m=re.search(r"src=\"([^\"]*assets/[^\"]+\.js)\"", html); print(m.group(1) if m else "")' 2>/dev/null || true)"
  if [[ -z "${asset_path}" ]]; then
    bad "${name}: cannot parse JS asset from index.html"
    return
  fi
  local result status content_type size
  result="$(curl --silent --show-error --output /dev/null --write-out '%{http_code} %{content_type} %{size_download}' --max-time 20 "${BASE_URL}${asset_path}" 2>&1)" || {
    bad "${name}: ${result}"
    return
  }
  status="$(awk '{print $1}' <<<"${result}")"
  content_type="$(awk '{print $2}' <<<"${result}")"
  size="$(awk '{print $3}' <<<"${result}")"
  if [[ "${status}" == "200" && "${content_type}" == application/javascript* && "${size}" -gt 100000 ]]; then
    ok "${name}: ${asset_path}"
  else
    bad "${name}: ${asset_path} -> HTTP ${status}, Content-Type ${content_type}, size ${size}"
  fi
}

echo "Health check target:"
echo "  frontend: ${BASE_URL}"
echo "  backend:  ${BACKEND_URL}"
echo

check_command "systemd service ${SERVICE_NAME} is active" \
  "${SUDO[@]}" systemctl is-active --quiet "${SERVICE_NAME}"

check_command "nginx service is active" \
  "${SUDO[@]}" systemctl is-active --quiet nginx

check_command "nginx config test" \
  "${SUDO[@]}" nginx -t

check_command "backend API health ${BACKEND_URL}/api/health" \
  curl --fail --silent --show-error --max-time 8 "${BACKEND_URL}/api/health"

check_command "nginx API proxy ${BASE_URL}/api/health" \
  curl --fail --silent --show-error --max-time 8 "${BASE_URL}/api/health"

check_command "system config status ${BASE_URL}/api/system/config-status" \
  curl --fail --silent --show-error --max-time 8 "${BASE_URL}/api/system/config-status"

check_json_endpoint "frontend config ${BASE_URL}/config.json" \
  "${BASE_URL}/config.json"

check_json_endpoint "frontend runtime config ${BASE_URL}/runtime-config.json" \
  "${BASE_URL}/runtime-config.json"

check_command "frontend home page ${BASE_URL}/" \
  curl --fail --silent --show-error --head --max-time 8 "${BASE_URL}/"

check_asset_endpoint "frontend JS asset" "${BASE_URL}/"

if "${SUDO[@]}" grep -R "__APP_ROOT__" /etc/nginx "/etc/systemd/system/${SERVICE_NAME}.service" >/tmp/esports-app-root-check 2>/dev/null; then
  bad "__APP_ROOT__ placeholder residue"
  cat /tmp/esports-app-root-check >&2
else
  ok "no __APP_ROOT__ residue"
fi
rm -f /tmp/esports-app-root-check

echo
echo "Summary: ${pass_count} passed, ${fail_count} failed"

if (( fail_count > 0 )); then
  echo
  echo "Troubleshooting:"
  echo "  bash scripts/view-logs.sh"
  echo "  sudo journalctl -u ${SERVICE_NAME} -n 200 --no-pager"
  echo "  sudo tail -n 200 /var/log/nginx/error.log"
  exit 1
fi
