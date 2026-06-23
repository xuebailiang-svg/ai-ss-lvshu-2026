#!/usr/bin/env bash
set -Eeuo pipefail

CITY="${1:-}"
ADDRESS="${2:-}"
AMAP_KEY="${AMAP_WEB_SERVICE_KEY:-}"
ENDPOINT="https://restapi.amap.com/v3/geocode/geo"

if [[ -z "${AMAP_KEY}" ]]; then
  echo "ERROR: AMAP_WEB_SERVICE_KEY is not configured." >&2
  echo "请先执行：export AMAP_WEB_SERVICE_KEY='你的高德Web服务Key'" >&2
  exit 2
fi

if [[ -z "${ADDRESS// }" ]]; then
  echo "ERROR: address is required." >&2
  echo "用法：bash scripts/check-amap-geocode.sh \"西安市\" \"雁塔区小寨西路\"" >&2
  exit 2
fi

mask_key() {
  local key="$1"
  local len=${#key}
  if (( len <= 8 )); then
    echo "***"
  else
    echo "${key:0:4}***${key: -4}"
  fi
}

tmp="$(mktemp)"
trap 'rm -f "${tmp}"' EXIT

curl_args=(
  --silent
  --show-error
  --get
  --connect-timeout 10
  --max-time 20
  --output "${tmp}"
  --write-out "%{http_code}"
  "${ENDPOINT}"
  --data-urlencode "key=${AMAP_KEY}"
  --data-urlencode "address=${ADDRESS}"
  --data-urlencode "output=JSON"
)
if [[ -n "${CITY// }" ]]; then
  curl_args+=(--data-urlencode "city=${CITY}")
fi

echo "Request:"
echo "  method: GET"
echo "  endpoint: ${ENDPOINT}"
echo "  key: $(mask_key "${AMAP_KEY}")"
echo "  city: ${CITY:-<not sent>}"
echo "  address: ${ADDRESS}"
echo "  output: JSON"

http_code="$(curl "${curl_args[@]}")"
echo "HTTP status: ${http_code}"

python3 - "${tmp}" <<'PY'
import json
import sys

path = sys.argv[1]
try:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
except Exception as exc:
    print(f"ERROR: failed to parse JSON response: {type(exc).__name__}: {exc}")
    sys.exit(1)

status = str(data.get("status", ""))
info = str(data.get("info", ""))
infocode = str(data.get("infocode", ""))
count = str(data.get("count", ""))

print("Amap response:")
print(f"  status: {status}")
print(f"  info: {info}")
print(f"  infocode: {infocode}")
print(f"  count: {count}")

geocodes = data.get("geocodes") or []
if not isinstance(geocodes, list):
    geocodes = []

print("Geocodes:")
for idx, row in enumerate(geocodes[:5], start=1):
    if not isinstance(row, dict):
        continue
    print(f"  - index: {idx}")
    print(f"    formatted_address: {row.get('formatted_address')}")
    print(f"    province: {row.get('province')}")
    print(f"    city: {row.get('city')}")
    print(f"    district: {row.get('district')}")
    print(f"    location: {row.get('location')}")
    print(f"    level: {row.get('level')}")

if status != "1" or infocode != "10000":
    print("Troubleshooting:")
    if infocode == "30001" or info == "ENGINE_RESPONSE_DATA_ERROR":
        print("  - 高德返回 ENGINE_RESPONSE_DATA_ERROR (30001)，优先检查 address 是否完整、city 是否传了区县/开发区，尝试不传 city 或把省市区写入 address。")
    elif "KEY" in info.upper() or infocode.startswith("100"):
        print("  - 可能是 Key 类型、接口权限、IP 白名单、签名、安全设置或配额问题；请确认使用的是 Web 服务 API Key。")
    else:
        print("  - 请检查服务器网络、DNS、防火墙、高德服务状态和请求参数。")
    sys.exit(1)

if count in {"", "0"} or not geocodes:
    print("Troubleshooting:")
    print("  - 高德请求成功但未解析到地址，请补充省、市、区、街道或门牌号。")
    sys.exit(1)
PY
