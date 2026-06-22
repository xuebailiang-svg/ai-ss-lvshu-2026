#!/usr/bin/env bash
set -Eeuo pipefail
APP_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE=/etc/esports-site-selection/backend.env
[[ -s "${ENV_FILE}" ]] || { echo "ERROR: ${ENV_FILE} 不存在。" >&2; exit 1; }
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a
mkdir -p "${APP_ROOT}/backups"
file="${APP_ROOT}/backups/site_selection_$(date +%Y%m%d_%H%M%S).sql.gz"
pg_dump "${DATABASE_URL}" | gzip >"${file}"
gzip -t "${file}"
echo "${file}"
