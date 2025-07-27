#!/bin/sh
# Railway 启动脚本 - 简化版
set -e

echo "[RAILWAY] 🚀 启动 YTDLP FastAPI 服务..."

# 使用 Railway 提供的 PORT 环境变量，默认 8000
PORT=${PORT:-8000}

echo "[RAILWAY] ✅ 使用端口: ${PORT}"
echo "[RAILWAY] 🚀 启动 uvicorn 服务器..."

# Railway 兼容启动命令
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --log-level info
