#!/usr/bin/env bash
# PanRadar 部署脚本 —— 在目标 ECS（Ubuntu/Debian/CentOS，root 运行）上执行
# 用法：把整个 pan-radar 目录上传到某临时目录后，在该目录运行：
#   sudo bash deploy/install.sh
set -euo pipefail

APP_DIR="/opt/panradar"
APP_USER="panradar"
PORT=8931
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"   # pan-radar 根目录

echo "==> 检查 python3"
command -v python3 >/dev/null || { echo "请先安装 python3（apt/yum install python3）"; exit 1; }
python3 --version

echo "==> 创建应用用户与目录"
id "$APP_USER" &>/dev/null || useradd -r -s /usr/sbin/nologin "$APP_USER"
mkdir -p "$APP_DIR"

echo "==> 拷贝代码（排除本地缓存/日志）"
rsync -a --exclude='data/panradar.db' --exclude='data/_*.log' --exclude='data/_*.done' \
      --exclude='.git' --exclude='__pycache__' "$SRC_DIR/" "$APP_DIR/" 2>/dev/null \
  || cp -r "$SRC_DIR/." "$APP_DIR/"
mkdir -p "$APP_DIR/data"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "==> 安装 systemd 服务"
cp "$SRC_DIR/deploy/panradar.service" /etc/systemd/system/panradar.service
systemctl daemon-reload
systemctl enable panradar
systemctl restart panradar
sleep 2

echo "==> 防火墙（若使用 ufw；阿里云还需在安全组放行）"
if command -v ufw >/dev/null; then
  ufw allow 80/tcp 2>/dev/null || true
  ufw allow 443/tcp 2>/dev/null || true
  ufw allow "$PORT"/tcp 2>/dev/null || true
fi

echo "==> 本机自检"
if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/" | grep -q 200; then
  echo "OK: 服务已在 http://127.0.0.1:$PORT/ 正常响应"
else
  echo "WARN: 本机自检未返回 200，查看日志： journalctl -u panradar -n 50 --no-pager"
fi
systemctl status panradar --no-pager || true
echo "部署脚本完成。公网访问请配置域名 + TLS（见 deploy/README.md）。"
