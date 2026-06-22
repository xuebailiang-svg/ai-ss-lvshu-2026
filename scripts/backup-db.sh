#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
test -f .env || { echo "ERROR: .env 不存在" >&2; exit 1; }
set -a; source .env; set +a
mkdir -p backups
file="backups/site_selection_$(date +%Y%m%d_%H%M%S).sql.gz"
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$file"
echo "$file"
