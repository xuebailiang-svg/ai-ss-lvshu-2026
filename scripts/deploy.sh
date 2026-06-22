#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
test -f .env || { echo "ERROR: .env 不存在，请先复制 .env.example 并填写配置"; exit 1; }
docker compose config --quiet
docker compose up -d --build
docker compose ps
echo "部署完成。请执行 scripts/health-check.sh 验证。"
