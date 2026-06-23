#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID}" -eq 0 ]]; then
  SUDO=()
else
  SUDO=(sudo)
fi

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

command -v "${SUDO[0]:-true}" >/dev/null 2>&1 || fail "需要 root 或 sudo。"
source /etc/os-release
[[ "${ID:-}" == "ubuntu" ]] || fail "仅支持 Ubuntu。"

APP_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_GROUP=esports-site-selection
APP_USER=esports-site-selection

echo "[1/7] 安装系统基础组件"
"${SUDO[@]}" apt-get update
"${SUDO[@]}" apt-get install -y \
  ca-certificates curl git gnupg openssl build-essential \
  python3 python3-venv python3-pip \
  nginx postgresql postgresql-contrib postgis

echo "[2/7] 检查 Python"
python3 - <<'PY'
import sys
assert sys.version_info >= (3, 10), f"需要 Python >= 3.10，当前为 {sys.version}"
print(sys.version)
PY

echo "[3/7] 检查 Node.js"
node_major=0
if command -v node >/dev/null 2>&1; then
  node_major="$(node -p 'process.versions.node.split(".")[0]')"
fi
if ((node_major < 20)) && [[ -s "${APP_ROOT}/frontend/dist/index.html" ]]; then
  echo "未检测到 Node.js 20+，但发现预构建 frontend/dist，本机将只负责运行静态文件。"
elif ((node_major < 20)); then
  echo "Node.js 缺失或低于 20，开始安装 Node.js 22。"
  "${SUDO[@]}" install -d -m 0755 /etc/apt/keyrings
  key_tmp="$(mktemp)"
  trap 'rm -f "${key_tmp}"' EXIT
  curl --fail --show-error --location --retry 5 --connect-timeout 15 \
    https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key -o "${key_tmp}"
  "${SUDO[@]}" gpg --dearmor --yes -o /etc/apt/keyrings/nodesource.gpg "${key_tmp}"
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" \
    | "${SUDO[@]}" tee /etc/apt/sources.list.d/nodesource.list >/dev/null
  "${SUDO[@]}" apt-get update
  "${SUDO[@]}" apt-get install -y nodejs
fi
if command -v node >/dev/null 2>&1; then node --version; fi
if command -v npm >/dev/null 2>&1; then npm --version; fi

echo "[4/7] 启动 PostgreSQL 和 Nginx"
"${SUDO[@]}" systemctl enable --now postgresql nginx
"${SUDO[@]}" systemctl is-active --quiet postgresql
"${SUDO[@]}" systemctl is-active --quiet nginx

echo "[5/7] 创建应用系统用户、用户组和目录"
if ! getent group "${APP_GROUP}" >/dev/null 2>&1; then
  "${SUDO[@]}" groupadd --system "${APP_GROUP}"
fi
if ! id "${APP_USER}" >/dev/null 2>&1; then
  "${SUDO[@]}" useradd --system --create-home \
    --home-dir /var/lib/esports-site-selection \
    --gid "${APP_GROUP}" \
    --shell /usr/sbin/nologin "${APP_USER}"
fi
"${SUDO[@]}" install -d -m 0750 -o root -g "${APP_GROUP}" /etc/esports-site-selection
"${SUDO[@]}" install -d -m 0750 -o "${APP_USER}" -g "${APP_GROUP}" /var/lib/esports-site-selection

current_user="${SUDO_USER:-${USER:-}}"
if [[ -n "${current_user}" && "${current_user}" != "root" ]]; then
  if id -nG "${current_user}" | tr ' ' '\n' | grep -qx "${APP_GROUP}"; then
    echo "当前登录用户 ${current_user} 已加入 ${APP_GROUP} 组。"
  else
    echo "当前登录用户 ${current_user} 尚未加入 ${APP_GROUP} 组，开始加入。"
    "${SUDO[@]}" usermod -aG "${APP_GROUP}" "${current_user}"
    echo "IMPORTANT: 组权限不会自动刷新到当前 SSH 会话。"
    echo "           请重新登录，或用下面命令执行部署："
    echo "           sg ${APP_GROUP} -c 'cd ${APP_ROOT} && bash scripts/deploy.sh'"
  fi
fi

echo "[6/7] 检查资源和端口"
df -h /
if ss -ltn | awk '{print $4}' | grep -Eq '(^|:)8000$'; then
  echo "WARNING: 端口 8000 已被占用，部署前需要停止旧后端服务或释放端口。"
fi
if ss -ltn | awk '{print $4}' | grep -Eq '(^|:)80$'; then
  echo "INFO: 端口 80 当前已有进程监听，部署脚本会安装并 reload Nginx 配置。"
fi

echo "[7/7] 前置环境验证完成"
echo "Python: $(python3 --version)"
echo "Node: $(command -v node >/dev/null 2>&1 && node --version || echo '使用预构建前端')"
echo "npm: $(command -v npm >/dev/null 2>&1 && npm --version || echo '使用预构建前端')"
echo "PostgreSQL: $(psql --version)"
echo "Nginx: $(nginx -v 2>&1)"
echo "下一步：创建数据库，运行 scripts/configure-secrets.sh，再执行 bash scripts/deploy.sh。"
