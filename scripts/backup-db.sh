#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${BACKEND_ENV_FILE:-/etc/esports-site-selection/backend.env}"
BACKUP_DIR="${BACKUP_DIR:-${APP_ROOT}/backups}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-}"

if [[ "${EUID}" -eq 0 ]]; then
  SUDO=()
else
  SUDO=(sudo)
fi

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

command -v pg_dump >/dev/null 2>&1 || fail "缺少 pg_dump，请先安装 postgresql-client 或运行 scripts/bootstrap-ubuntu-direct.sh。"
command -v gzip >/dev/null 2>&1 || fail "缺少 gzip。"

if ! "${SUDO[@]}" test -s "${ENV_FILE}"; then
  fail "${ENV_FILE} 不存在或为空，无法读取 DATABASE_URL。"
fi
if ! "${SUDO[@]}" grep -Eq '^DATABASE_URL=.+$' "${ENV_FILE}"; then
  fail "${ENV_FILE} 缺少 DATABASE_URL。"
fi

mkdir -p "${BACKUP_DIR}"
backup_file="${BACKUP_DIR}/site_selection_$(date +%Y%m%d_%H%M%S).sql.gz"
tmp_file="${backup_file}.tmp"

cleanup() {
  rm -f "${tmp_file}"
}
trap cleanup EXIT

echo "开始备份数据库，输出目录：${BACKUP_DIR}"
echo "注意：脚本不会打印 DATABASE_URL 或数据库密码。"

if [[ -r "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
  [[ -n "${DATABASE_URL:-}" ]] || fail "DATABASE_URL 为空。"
  pg_dump "${DATABASE_URL}" | gzip >"${tmp_file}"
else
  "${SUDO[@]}" bash -c "set -Eeuo pipefail; set -a; source '${ENV_FILE}'; set +a; pg_dump \"\${DATABASE_URL}\"" | gzip >"${tmp_file}"
fi

gzip -t "${tmp_file}"
mv "${tmp_file}" "${backup_file}"
chmod 0600 "${backup_file}"

if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
  chown "${SUDO_USER}:${SUDO_USER}" "${backup_file}" 2>/dev/null || true
fi

echo "备份完成：${backup_file}"

if [[ -n "${KEEP_DAYS}" ]]; then
  if [[ "${KEEP_DAYS}" =~ ^[0-9]+$ ]]; then
    find "${BACKUP_DIR}" -type f -name 'site_selection_*.sql.gz' -mtime "+${KEEP_DAYS}" -print -delete
  else
    echo "WARNING: BACKUP_KEEP_DAYS 不是数字，跳过自动清理。"
  fi
fi
