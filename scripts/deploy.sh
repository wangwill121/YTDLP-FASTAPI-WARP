#!/bin/bash
# Railway 部署脚本

echo "🚂 准备 Railway 部署..."

# 检查必要文件
if [ ! -f "requirements.txt" ]; then
    echo "❌ requirements.txt 不存在"
    exit 1
fi

if [ ! -f "Dockerfile" ]; then
    echo "❌ Dockerfile 不存在"
    exit 1
fi

# 检查环境变量
if [ -z "$SECRET_KEY" ]; then
    echo "❌ 请设置 SECRET_KEY 环境变量"
    exit 1
fi

echo "✅ 环境检查通过"
echo "📦 准备提交代码..."

# 添加所有更改
git add .

# 提交更改
git commit -m "Deploy: $(date '+%Y-%m-%d %H:%M:%S')"

echo "🚀 推送到 Railway..."
git push origin main

echo "✅ 部署完成！"
echo "📱 访问你的应用: https://your-app.railway.app"
