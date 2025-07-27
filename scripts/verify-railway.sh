#!/bin/sh
# Railway 部署验证脚本

echo "🔍 Railway 部署配置验证"
echo "=========================="

# 检查端口配置
if [ -z "$PORT" ]; then
    echo "⚠️  PORT 环境变量未设置，使用默认值 8000"
    export PORT=8000
else
    echo "✅ PORT 已设置: $PORT"
fi

# 检查关键环境变量
echo "\n📋 环境变量检查:"
echo "- DIRECT_LINK_MODE: ${DIRECT_LINK_MODE:-'未设置'}"
echo "- ENABLE_WARP_PROXY: ${ENABLE_WARP_PROXY:-'未设置'}"
echo "- DISABLE_HOST_VALIDATION: ${DISABLE_HOST_VALIDATION:-'未设置'}"
echo "- ALLOWED_HOSTS: ${ALLOWED_HOSTS:-'未设置'}"

# 检查必要文件
echo "\n📁 文件检查:"
if [ -f "/code/app/main.py" ]; then
    echo "✅ main.py 存在"
else
    echo "❌ main.py 不存在"
    exit 1
fi

if [ -d "/code/warp-configs" ]; then
    echo "✅ warp-configs 目录存在"
    echo "   配置文件数量: $(ls -1 /code/warp-configs/*.conf 2>/dev/null | wc -l)"
else
    echo "⚠️  warp-configs 目录不存在"
fi

# 测试 Python 导入
echo "\n🐍 Python 导入测试:"
cd /code
if python3 -c "from app.main import app; print('✅ 应用导入成功')"; then
    echo "✅ FastAPI 应用可以正常导入"
else
    echo "❌ FastAPI 应用导入失败"
    exit 1
fi

echo "\n🚀 验证完成，准备启动服务..." 