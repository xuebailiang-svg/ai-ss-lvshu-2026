#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec bash "${ROOT_DIR}/scripts/install.sh" "$@"
