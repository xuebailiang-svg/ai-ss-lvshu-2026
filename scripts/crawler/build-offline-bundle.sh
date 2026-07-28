#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
OUTPUT="${1:-${SOURCE_ROOT}/crawler/esports-crawler-offline-ubuntu22.04-amd64.tar.gz}"
WORK_DIR="$(mktemp -d /tmp/esports-crawler-bundle.XXXXXX)"
BUNDLE_DIR="${WORK_DIR}/esports-crawler-offline"

cleanup() { rm -rf "${WORK_DIR}"; }
trap cleanup EXIT

command -v python3 >/dev/null || { echo "ERROR: 缺少 python3" >&2; exit 1; }
command -v tar >/dev/null || { echo "ERROR: 缺少 tar" >&2; exit 1; }

mkdir -p "${BUNDLE_DIR}/wheelhouse" "${BUNDLE_DIR}/ms-playwright" "${BUNDLE_DIR}/debs"
python3 -m venv "${WORK_DIR}/venv"
"${WORK_DIR}/venv/bin/python" -m pip install --upgrade pip
"${WORK_DIR}/venv/bin/pip" download \
  --dest "${BUNDLE_DIR}/wheelhouse" \
  -r "${SOURCE_ROOT}/backend/requirements.txt" \
  -r "${SOURCE_ROOT}/crawler/requirements.txt"
"${WORK_DIR}/venv/bin/pip" install \
  --no-index \
  --find-links "${BUNDLE_DIR}/wheelhouse" \
  -r "${SOURCE_ROOT}/crawler/requirements.txt"
PLAYWRIGHT_BROWSERS_PATH="${BUNDLE_DIR}/ms-playwright" \
  "${WORK_DIR}/venv/bin/python" -m playwright install chromium
"${WORK_DIR}/venv/bin/pip" freeze >"${BUNDLE_DIR}/resolved-python-requirements.txt"
cp "${SOURCE_ROOT}/crawler/requirements.txt" "${BUNDLE_DIR}/crawler-requirements.txt"
cp "${SOURCE_ROOT}/backend/requirements.txt" "${BUNDLE_DIR}/backend-requirements.txt"
cp "${SCRIPT_DIR}/ubuntu-22.04-packages.txt" "${BUNDLE_DIR}/ubuntu-22.04-packages.txt"

if command -v apt-get >/dev/null; then
  echo "==> 下载 Ubuntu 22.04 Chromium 运行依赖"
  while IFS= read -r package; do
    [[ -n "${package}" ]] || continue
    (cd "${BUNDLE_DIR}/debs" && apt-get download "${package}") || {
      echo "WARNING: 无法下载 ${package}，目标服务器可联网时由安装脚本补装" >&2
    }
  done <"${SCRIPT_DIR}/ubuntu-22.04-packages.txt"
fi

cat >"${BUNDLE_DIR}/MANIFEST.txt" <<EOF
bundle_format=1
platform=ubuntu-22.04-amd64
created_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
python=$(python3 --version 2>&1)
EOF

mkdir -p "$(dirname "${OUTPUT}")"
tar -C "${WORK_DIR}" -czf "${OUTPUT}" esports-crawler-offline
echo "OK: 离线包已生成：${OUTPUT}"
echo "服务器安装：sudo bash scripts/crawler/install.sh --bundle /上传路径/$(basename "${OUTPUT}")"
