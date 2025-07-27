#!/bin/bash

# 设置错误时退出
set -e

echo "🚀 YTDLP FastAPI 服务启动中..."

# Set the default port if not defined
PORT=${PORT:-8000}
echo "🔧 使用端口: $PORT"

# 为Railway环境优化worker数量
if [ "$RAILWAY_ENVIRONMENT" = "production" ] || [ -n "$RAILWAY_PROJECT_ID" ]; then
    # Railway 环境使用单worker模式以避免资源竞争
    WORKERS=1
    echo "🚂 Railway 生产环境检测到，使用单worker模式"
else
    # 本地开发环境计算合适的worker数量
    if command -v nproc >/dev/null 2>&1; then
        # Linux/Unix with nproc
        WORKERS=$(( $(nproc) * 2 + 1 ))
    elif command -v sysctl >/dev/null 2>&1; then
        # macOS
        WORKERS=$(( $(sysctl -n hw.logicalcpu) * 2 + 1 ))
    else
        # Fallback to single worker
        WORKERS=1
    fi
fi

echo "📊 端口: $PORT"
echo "⚡ 工作进程: $WORKERS"
echo "🔧 模式: ${RAILWAY_ENVIRONMENT:-development}"

# 在Docker环境中直接使用python3，避免兼容性问题
PYTHON_CMD="python3"
echo "🐍 使用 Python 命令: $PYTHON_CMD"

# 启动服务
exec $PYTHON_CMD -m uvicorn app.main:app --workers $WORKERS --host=0.0.0.0 --port="$PORT"
