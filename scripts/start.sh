#!/bin/bash

# Set the default port if not defined
PORT=${PORT:-8000}

# Calculate the number of workers (macOS compatible)
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

echo "🚀 启动 FastAPI 服务..."
echo "📊 端口: $PORT"
echo "⚡ 工作进程: $WORKERS"

# Run the uvicorn server with the specified settings
uvicorn app.main:app --workers $WORKERS --host=0.0.0.0 --port="$PORT" --loop uvloop --http h11
