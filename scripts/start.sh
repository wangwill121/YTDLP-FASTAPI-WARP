#!/bin/bash

# Set the default port if not defined
PORT=${PORT:-8000}

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

echo "🚀 启动 FastAPI 服务..."
echo "📊 端口: $PORT"
echo "⚡ 工作进程: $WORKERS"
echo "🔧 模式: ${RAILWAY_ENVIRONMENT:-development}"

# Run the uvicorn server with the specified settings
uvicorn app.main:app --workers $WORKERS --host=0.0.0.0 --port="$PORT" --loop uvloop --http h11
