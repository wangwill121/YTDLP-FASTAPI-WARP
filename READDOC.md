# 📖 YTDLP FastAPI 使用文档

> **完整的部署、配置和使用指南**

## 📋 目录

- [1. 快速部署](#1-快速部署)
- [2. 环境配置](#2-环境配置)
- [3. API 使用指南](#3-api-使用指南)
- [4. 监控和维护](#4-监控和维护)
- [5. 故障排除](#5-故障排除)
- [6. 性能优化](#6-性能优化)

## 1. 快速部署

### 🚂 Railway 部署（推荐）

**最简单的一键部署方式：**

```bash
# 1. 克隆项目
git clone <your-repo-url>
cd ytdlp-fastapi

# 2. 部署到 Railway
railway login
railway init
railway up
```

**或者通过 GitHub 连接：**

1. 将代码推送到 GitHub 仓库
2. 在 Railway 控制台连接 GitHub 仓库
3. 配置环境变量（见下节）
4. 自动部署完成

### 🐳 Docker 本地部署

```bash
# 构建镜像
docker build -t ytdlp-fastapi .

# 运行容器
docker run -d \
  -p 8000:8000 \
  -e SECRET_KEY=your-secret-key \
  -e ALLOWED_HOSTS=localhost,yourdomain.com \
  -e DIRECT_LINK_MODE=1 \
  -e ENABLE_WARP_PROXY=1 \
  --name ytdlp-api \
  ytdlp-fastapi
```

### 🐍 本地开发部署

```bash
# 安装依赖
pip install -r requirements.txt

# 创建环境配置
cp .env.example .env
# 编辑 .env 文件

# 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 2. 环境配置

### 🔑 核心环境变量

在 Railway 项目的 **Variables** 标签页中添加：

#### 必填配置

| 变量名 | 示例值 | 说明 |
|--------|--------|------|
| `SECRET_KEY` | `my-super-secret-key-2024` | 主 API 密钥，32-64位随机字符串 |
| `ALLOWED_HOSTS` | `mysite.com,*.railway.app` | 允许访问的域名白名单 |
| `DIRECT_LINK_MODE` | `1` | 直链模式开关（推荐保持为1） |
| `ENABLE_WARP_PROXY` | `1` | 启用 WARP 代理系统 |

#### 高级配置

| 变量名 | 示例值 | 说明 |
|--------|--------|------|
| `MULTI_DOMAIN_KEYS` | `site1.com:key123,*.vercel.app:key456` | 多域名多密钥配置 |
| `WARP_CONFIG_DIR` | `warp-configs` | WARP 配置文件目录 |
| `PROXY_HEALTH_CHECK_INTERVAL` | `300` | 代理健康检查间隔（秒） |
| `DISABLE_TURNSTILE` | `1` | 禁用人机验证（简化配置） |
| `DISABLE_HOST_VALIDATION` | `1` | 禁用额外Host校验 |

### 🔐 密钥生成

#### SECRET_KEY 生成

**方法1: Python 生成**
```python
import secrets
import string

alphabet = string.ascii_letters + string.digits
secret_key = ''.join(secrets.choice(alphabet) for _ in range(32))
print(f"SECRET_KEY={secret_key}")
```

**方法2: 在线工具**
- 访问：https://www.uuidgenerator.net/
- 或：https://passwordsgenerator.net/
- 生成 32-64 位随机字符串

**方法3: 命令行**
```bash
# macOS/Linux
openssl rand -base64 32
# 或
uuidgen | tr -d '-'
```

#### 多域名配置示例

```env
SECRET_KEY=main-key-for-all-domains
MULTI_DOMAIN_KEYS=site1.com:site1key,site2.com:site2key,*.vercel.app:vercelkey
```

这样配置后：
- `site1.com` 可使用 `site1key` 或主密钥
- `site2.com` 可使用 `site2key` 或主密钥  
- `*.vercel.app` 可使用 `vercelkey` 或主密钥

### 📊 WARP 系统配置

WARP 系统会自动：
1. 生成 8 个真实的 Cloudflare WARP 配置
2. 定期健康检查（每5分钟）
3. 自动清理不健康配置并补充新配置
4. 根据负载动态扩容（最多15个配置）

**默认限制（免费账户安全范围）：**
- 目标配置数：8个
- 最大并发：32个（8配置×4并发）
- QPS 限制：2.5 请求/秒
- 动态扩容上限：15个配置

## 3. API 使用指南

### 📡 接口概览

| 端点 | 方法 | 描述 | 鉴权 | 说明 |
|------|------|------|------|------|
| `/healthz` | GET | 健康检查 | ❌ | 基础服务状态 |
| `/status` | GET | 系统状态 | ❌ | CPU、内存、磁盘信息 |
| `/concurrency` | GET | 并发状态 | ❌ | 当前并发和队列状态 |
| `/warp-optimization` | GET | WARP 状态 | ❌ | WARP 配置池状态 |
| `/warp-optimization/force` | POST | 强制优化 | ❌ | 手动触发 WARP 优化 |
| `/test-video` | GET | 测试解析 | ❌ | 测试视频解析功能 |
| `/v1/video/{video_id}` | GET | 视频解析 | ✅ | 核心视频解析 API |

### 🎬 视频解析 API

#### 基础调用

```javascript
const response = await fetch('https://your-api.railway.app/v1/video/dQw4w9WgXcQ', {
  headers: {
    'X-Secret': 'your-secret-key'
  }
});

const data = await response.json();
console.log(data);
```

#### 响应格式

```json
{
  "video_url": "https://rr2---sn-xxx.googlevideo.com/videoplayback?...",
  "audio_url": "https://rr1---sn-xxx.googlevideo.com/videoplayback?...",
  "video_id": "dQw4w9WgXcQ",
  "title": "Rick Astley - Never Gonna Give You Up (Official Video)",
  "duration": 212
}
```

#### 错误处理

```javascript
try {
  const response = await fetch('/v1/video/invalid_id', {
    headers: { 'X-Secret': 'your-key' }
  });
  
  if (!response.ok) {
    switch (response.status) {
      case 401:
        throw new Error('API 密钥无效');
      case 400:
        throw new Error('域名不在白名单中');
      case 404:
        throw new Error('视频不存在或无法解析');
      case 429:
        throw new Error('请求过于频繁，请稍后重试');
      case 500:
        throw new Error('服务器内部错误');
      default:
        throw new Error(`请求失败: ${response.status}`);
    }
  }
  
  const data = await response.json();
  return data;
} catch (error) {
  console.error('视频解析失败:', error.message);
}
```

### 🔧 React 集成示例

#### 自定义 Hook

```javascript
import { useState, useEffect } from 'react';

export function useVideoLinks(videoId, apiKey, apiUrl) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!videoId || !apiKey) return;
    
    setLoading(true);
    setError(null);
    
    fetch(`${apiUrl}/v1/video/${videoId}`, {
      headers: { 'X-Secret': apiKey }
    })
    .then(async res => {
      if (!res.ok) {
        const errorText = await res.text();
        throw new Error(`HTTP ${res.status}: ${errorText}`);
      }
      return res.json();
    })
    .then(setData)
    .catch(setError)
    .finally(() => setLoading(false));
  }, [videoId, apiKey, apiUrl]);

  return { 
    videoUrl: data?.video_url,
    audioUrl: data?.audio_url,
    title: data?.title,
    duration: data?.duration,
    loading, 
    error 
  };
}
```

#### 视频播放器组件

```javascript
import React from 'react';
import { useVideoLinks } from './hooks/useVideoLinks';

function VideoPlayer({ videoId, className }) {
  const { videoUrl, audioUrl, title, loading, error } = useVideoLinks(
    videoId,
    process.env.NEXT_PUBLIC_YTDLP_API_KEY,
    process.env.NEXT_PUBLIC_YTDLP_API_URL
  );
  
  if (loading) {
    return (
      <div className={`${className} flex items-center justify-center bg-gray-100`}>
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto"></div>
          <p className="mt-2 text-sm text-gray-600">解析视频中...</p>
        </div>
      </div>
    );
  }
  
  if (error) {
    return (
      <div className={`${className} flex items-center justify-center bg-red-50 border border-red-200`}>
        <div className="text-center text-red-600">
          <p className="font-medium">解析失败</p>
          <p className="text-sm">{error.message}</p>
        </div>
      </div>
    );
  }
  
  if (!videoUrl || !audioUrl) {
    return (
      <div className={`${className} flex items-center justify-center bg-gray-100`}>
        <p className="text-gray-500">暂无视频数据</p>
      </div>
    );
  }
  
  return (
    <div className={className}>
      {title && (
        <h3 className="text-lg font-medium mb-3 text-gray-900">{title}</h3>
      )}
      
      {/* 视频播放器 */}
      <div className="space-y-3">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            视频 (无声)
          </label>
          <video 
            src={videoUrl} 
            controls 
            className="w-full rounded-lg shadow-sm"
            preload="metadata"
          />
        </div>
        
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            音频
          </label>
          <audio 
            src={audioUrl} 
            controls 
            className="w-full"
            preload="metadata"
          />
        </div>
      </div>
    </div>
  );
}

export default VideoPlayer;
```

### 📱 Next.js API Route 示例

```javascript
// pages/api/video/[id].js 或 app/api/video/[id]/route.js

export async function GET(request, { params }) {
  const { id } = params;
  
  if (!id) {
    return Response.json({ error: 'Video ID is required' }, { status: 400 });
  }
  
  try {
    const response = await fetch(
      `${process.env.YTDLP_API_URL}/v1/video/${id}`,
      {
        headers: {
          'X-Secret': process.env.YTDLP_SECRET_KEY,
        },
      }
    );
    
    if (!response.ok) {
      const errorText = await response.text();
      return Response.json(
        { error: `API request failed: ${response.status} ${errorText}` },
        { status: response.status }
      );
    }
    
    const data = await response.json();
    
    // 可选：添加缓存头
    return Response.json(data, {
      headers: {
        'Cache-Control': 'public, max-age=300', // 缓存5分钟
      },
    });
    
  } catch (error) {
    console.error('Video API error:', error);
    return Response.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
```

## 4. 监控和维护

### 📊 系统监控

#### 健康检查命令

```bash
# 基础健康检查
curl https://your-app.railway.app/healthz

# 详细系统状态
curl https://your-app.railway.app/status

# 并发控制状态
curl https://your-app.railway.app/concurrency

# WARP 优化状态
curl https://your-app.railway.app/warp-optimization

# 测试视频解析功能
curl https://your-app.railway.app/test-video
```

#### 监控脚本

```bash
#!/bin/bash
# monitor.sh - 系统监控脚本

API_URL="https://your-app.railway.app"

echo "📊 YTDLP API 系统监控报告 - $(date)"
echo "=================================="

# 1. 基础健康检查
echo "🔍 基础健康检查:"
curl -s "$API_URL/healthz" | jq '.status' || echo "❌ 健康检查失败"

# 2. 并发状态
echo -e "\n⚡ 并发控制状态:"
CONCURRENCY=$(curl -s "$API_URL/concurrency")
echo "$CONCURRENCY" | jq '{
  active_requests: .current_status.active_requests,
  queued_requests: .current_status.queued_requests,
  max_concurrent: .cloudflare_limits.total_max_concurrent,
  queue_usage: (.current_status.queued_requests / .config.max_queue_size * 100)
}'

# 3. WARP 状态
echo -e "\n🔧 WARP 配置状态:"
WARP_STATUS=$(curl -s "$API_URL/warp-optimization")
echo "$WARP_STATUS" | jq '{
  healthy_configs: .current_status.healthy_configs,
  unhealthy_configs: .current_status.unhealthy_configs,
  total_configs: .current_status.total_configs,
  target_configs: .optimization_config.target_config_count
}'

# 4. 系统资源
echo -e "\n💻 系统资源:"
SYSTEM_STATUS=$(curl -s "$API_URL/status")
echo "$SYSTEM_STATUS" | jq '{
  cpu_percent: .system.cpu_percent,
  memory_percent: .system.memory.percent,
  disk_percent: .system.disk.percent
}'

echo -e "\n✅ 监控完成"
```

### 🚨 告警配置

#### 关键指标阈值

| 指标 | 健康范围 | 警告阈值 | 严重阈值 |
|------|----------|----------|----------|
| CPU 使用率 | < 70% | 70-85% | > 85% |
| 内存使用率 | < 80% | 80-90% | > 90% |
| 并发使用率 | < 60% | 60-80% | > 80% |
| 队列使用率 | < 40% | 40-60% | > 60% |
| 健康配置数 | ≥ 5个 | 3-4个 | < 3个 |
| 请求成功率 | > 95% | 90-95% | < 90% |

#### 自动告警脚本

```bash
#!/bin/bash
# alert.sh - 自动告警脚本

API_URL="https://your-app.railway.app"
WEBHOOK_URL="YOUR_SLACK_OR_DISCORD_WEBHOOK"

check_critical_metrics() {
    # 检查健康配置数
    HEALTHY_CONFIGS=$(curl -s "$API_URL/warp-optimization" | jq '.current_status.healthy_configs')
    if [ "$HEALTHY_CONFIGS" -lt 3 ]; then
        send_alert "🔴 严重告警: WARP 健康配置仅剩 $HEALTHY_CONFIGS 个，建议立即检查"
    fi
    
    # 检查并发使用率
    CONCURRENCY_DATA=$(curl -s "$API_URL/concurrency")
    ACTIVE=$(echo "$CONCURRENCY_DATA" | jq '.current_status.active_requests')
    MAX_CONCURRENT=$(echo "$CONCURRENCY_DATA" | jq '.cloudflare_limits.total_max_concurrent')
    USAGE=$((ACTIVE * 100 / MAX_CONCURRENT))
    
    if [ "$USAGE" -gt 80 ]; then
        send_alert "🟡 警告: 并发使用率达到 $USAGE%，接近上限"
    fi
}

send_alert() {
    local message="$1"
    echo "$message"
    
    # 发送到 Slack/Discord
    curl -X POST -H 'Content-type: application/json' \
        --data "{\"text\":\"$message\"}" \
        "$WEBHOOK_URL"
}

# 每5分钟检查一次
while true; do
    check_critical_metrics
    sleep 300
done
```

## 5. 故障排除

### 🔧 常见问题解决

#### 1. API 鉴权失败

**症状**: 返回 401 Unauthorized

**解决方案**:
```bash
# 检查密钥配置
curl -H "X-Secret: your-secret-key" \
     https://your-app.railway.app/healthz

# 如果还是失败，检查 Railway 环境变量
railway variables
```

**多域名鉴权问题**:
```javascript
// 确保 Referer 头部正确
fetch('/v1/video/videoId', {
  headers: {
    'X-Secret': 'domain-specific-key',
    'Referer': 'https://yourdomain.com'  // 必须与配置的域名匹配
  }
});
```

#### 2. WARP 配置全部失效

**症状**: WARP 健康配置为 0

**解决方案**:
```bash
# 1. 检查当前状态
curl https://your-app.railway.app/warp-optimization

# 2. 强制重新优化
curl -X POST https://your-app.railway.app/warp-optimization/force

# 3. 如果还是失败，重启应用
railway redeploy

# 4. 检查网络连接（可能是 Cloudflare API 限制）
# 等待5-10分钟后再次尝试
```

#### 3. 视频解析超时

**症状**: 请求超时或响应时间过长

**解决方案**:
```bash
# 1. 检查系统状态
curl https://your-app.railway.app/status

# 2. 检查是否队列积压
curl https://your-app.railway.app/concurrency

# 3. 如果队列积压严重，等待自然消化或重启
railway restart

# 4. 检查特定视频是否可解析
curl https://your-app.railway.app/test-video
```

#### 4. 并发限制触发

**症状**: 请求被排队或拒绝

**解决方案**:
```bash
# 检查当前并发状态
CONCURRENCY=$(curl -s https://your-app.railway.app/concurrency)
echo "$CONCURRENCY" | jq '{
  active: .current_status.active_requests,
  queued: .current_status.queued_requests,
  max: .cloudflare_limits.total_max_concurrent
}'

# 如果确实需要更高并发，考虑：
# 1. 等待当前请求完成
# 2. 升级 Cloudflare 账户
# 3. 优化客户端请求频率
```

### 📝 日志分析

#### Railway 日志查看

```bash
# 查看实时日志
railway logs

# 查看最近的日志
railway logs --tail 100

# 过滤特定关键字
railway logs | grep "ERROR\|WARN"
```

#### 关键日志信息

- `🚀 YTDLP FastAPI 启动中...` - 应用正常启动
- `⚡ 并发控制: 已启用` - 并发系统初始化
- `🔧 WARP 优化: 已启用` - WARP 系统启动
- `ERROR` - 错误信息，需要关注
- `WARNING` - 警告信息，可能需要处理

## 6. 性能优化

### 🚀 客户端优化

#### 请求优化

```javascript
// 1. 实现请求缓存
const videoCache = new Map();

async function getCachedVideoInfo(videoId, apiKey) {
  const cacheKey = videoId;
  
  // 检查缓存
  if (videoCache.has(cacheKey)) {
    const cached = videoCache.get(cacheKey);
    // 缓存5分钟
    if (Date.now() - cached.timestamp < 300000) {
      return cached.data;
    }
  }
  
  // 请求新数据
  const data = await fetchVideoInfo(videoId, apiKey);
  
  // 存储到缓存
  videoCache.set(cacheKey, {
    data,
    timestamp: Date.now()
  });
  
  return data;
}

// 2. 实现请求队列
class RequestQueue {
  constructor(concurrency = 3) {
    this.concurrency = concurrency;
    this.running = 0;
    this.queue = [];
  }
  
  async add(requestFn) {
    return new Promise((resolve, reject) => {
      this.queue.push({ requestFn, resolve, reject });
      this.tryNext();
    });
  }
  
  async tryNext() {
    if (this.running >= this.concurrency || this.queue.length === 0) {
      return;
    }
    
    this.running++;
    const { requestFn, resolve, reject } = this.queue.shift();
    
    try {
      const result = await requestFn();
      resolve(result);
    } catch (error) {
      reject(error);
    } finally {
      this.running--;
      this.tryNext();
    }
  }
}

const requestQueue = new RequestQueue(2); // 最多同时2个请求

// 使用队列
async function fetchVideoWithQueue(videoId, apiKey) {
  return requestQueue.add(() => fetchVideoInfo(videoId, apiKey));
}
```

#### 错误重试机制

```javascript
async function fetchWithRetry(url, options, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const response = await fetch(url, options);
      
      if (response.ok) {
        return response.json();
      }
      
      // 对于 429 (Too Many Requests)，等待更长时间
      if (response.status === 429) {
        const waitTime = Math.min(1000 * Math.pow(2, i), 10000); // 指数退避，最多10秒
        await new Promise(resolve => setTimeout(resolve, waitTime));
        continue;
      }
      
      // 对于其他错误，抛出异常
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      
    } catch (error) {
      if (i === maxRetries - 1) {
        throw error;
      }
      
      // 等待后重试
      const waitTime = 1000 * (i + 1);
      await new Promise(resolve => setTimeout(resolve, waitTime));
    }
  }
}
```

### ⚡ 服务端优化

#### Railway 配置优化

```toml
# railway.toml
[build]
command = "pip install -r requirements.txt"

[deploy]
healthcheckPath = "/healthz"
healthcheckTimeout = 30
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 3

[env]
# 优化 Python 性能
PYTHONUNBUFFERED = "1"
PYTHONDONTWRITEBYTECODE = "1"

# 优化 uvicorn 性能
WEB_CONCURRENCY = "4"  # 4个工作进程
MAX_WORKERS = "4"
```

#### 应用性能调优

如果升级到付费 Cloudflare 账户，可以调整配置：

```python
# 在 app/main.py 中调整
concurrency_config = ConcurrencyConfig(
    account_tier=AccountTier.STANDARD,  # 或 ENTERPRISE
    max_queue_size=100,                 # 增加队列大小
    request_timeout=60.0,               # 增加超时时间
    max_concurrent_override=50          # 自定义并发数
)

warp_opt_config = WARPOptimizationConfig(
    target_config_count=15,             # 增加目标配置数
    max_config_count=25,               # 增加最大配置数
    cleanup_interval=180,              # 缩短清理间隔
    health_check_timeout=10.0          # 缩短健康检查超时
)
```

### 📈 扩展建议

#### 水平扩展

1. **多实例部署**: Railway 支持多实例部署
2. **负载均衡**: 使用 Railway 内置负载均衡
3. **区域部署**: 不同地区部署提升全球访问速度

#### 监控集成

```javascript
// 添加性能监控
function trackApiPerformance(apiCall) {
  const startTime = Date.now();
  
  return apiCall()
    .then(result => {
      const duration = Date.now() - startTime;
      
      // 发送到分析服务
      analytics.track('api_call_success', {
        duration,
        endpoint: 'video_parse'
      });
      
      return result;
    })
    .catch(error => {
      const duration = Date.now() - startTime;
      
      analytics.track('api_call_error', {
        duration,
        error: error.message,
        endpoint: 'video_parse'
      });
      
      throw error;
    });
}
```

---

## 🎉 总结

这份文档涵盖了 YTDLP FastAPI 项目的完整使用流程，从部署到监控的所有细节。遵循这些指南，您可以：

- ✅ 快速部署高性能的视频解析服务
- ✅ 实现稳定的并发控制和 WARP 管理
- ✅ 建立完善的监控和告警体系
- ✅ 优化客户端和服务端性能

如有问题，请参考故障排除部分或查看项目的 GitHub Issues。

**🚀 祝您的 YouTube 解析服务运行顺利！** 