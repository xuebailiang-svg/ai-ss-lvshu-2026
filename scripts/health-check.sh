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

check_command "frontend home page ${BASE_URL}/" \
  curl --fail --silent --show-error --head --max-time 8 "${BASE_URL}/"

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
