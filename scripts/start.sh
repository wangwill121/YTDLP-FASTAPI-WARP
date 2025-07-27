#!/bin/sh
# Exit on error
set -e

# 运行 Railway 验证脚本
if [ -f "/code/scripts/verify-railway.sh" ]; then
    echo "[DEBUG] 运行 Railway 验证..."
    sh /code/scripts/verify-railway.sh
fi

# Canary log - a simple message to confirm the script is running
echo "[DEBUG] boot script started."

# 使用 Railway 提供的 PORT 环境变量，默认 8000
PORT=${PORT:-8000}
WORKERS=1

echo "[DEBUG] PORT=${PORT}"
echo "[DEBUG] WORKERS=${WORKERS}"
echo "[DEBUG] Launching Uvicorn..."

# Railway 兼容的启动命令：绑定到所有接口包括 IPv6
# 根据 Railway 文档，需要同时支持 IPv4 和 IPv6
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers ${WORKERS} --log-level info 2>&1
