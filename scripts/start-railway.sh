#!/bin/sh
# Railway 专用启动脚本
set -e

echo "[RAILWAY] Starting YTDLP FastAPI service..."

# Railway 会自动设置 PORT 环境变量
PORT=${PORT:-8000}

echo "[RAILWAY] Using PORT: ${PORT}"
echo "[RAILWAY] Starting uvicorn server..."

# Railway 推荐的配置：
# - 使用 0.0.0.0 绑定所有接口
# - 使用动态端口
# - 单个 worker (Railway 会处理横向扩展)
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --log-level info 