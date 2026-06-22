#!/usr/bin/env bash
set -Eeuo pipefail
BASE_URL="${APP_BASE_URL:-http://localhost}"
for i in {1..30}; do
  if curl --fail --silent --show-error "$BASE_URL/api/health"; then echo; exit 0; fi
  sleep 2
done
echo "ERROR: health check failed after 60 seconds" >&2
exit 1
