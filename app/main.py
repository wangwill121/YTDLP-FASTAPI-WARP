from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.middleware.node import NodeMiddleware
from app.middleware.process_time import ProcessTimeMiddleware
from app.middleware.referer import RefererCheckMiddleware

from asgi_correlation_id import CorrelationIdMiddleware

from app.routes import router
from app.utils.config import settings
import asyncio
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Lifespan context manager for startup and shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理器 - 处理启动和关闭事件"""
    
    # 存储清理任务的引用
    cleanup_task = None
    
    try:
        # === 应用启动 ===
        logger.info("🚀 启动 YTDLP FastAPI 服务...")
        logger.info(f"📊 直链模式: {'启用' if settings.DIRECT_LINK_MODE else '禁用'}")
        logger.info(f"🔐 允许的域名: {settings.ALLOWED_HOSTS}")
        logger.info(f"🔧 WARP 代理: {'启用' if settings.ENABLE_WARP_PROXY else '禁用'}")
        
        # 1. 初始化并发控制系统（两种模式都需要）
        try:
            from app.utils.concurrency_limiter import get_concurrency_limiter, start_cleanup_task, ConcurrencyConfig, AccountTier
            
            concurrency_config = ConcurrencyConfig(
                account_tier=AccountTier.FREE,
                max_queue_size=50,
                request_timeout=45.0
            )
            limiter = get_concurrency_limiter(concurrency_config)
            
            # 启动并发控制清理任务
            cleanup_task = asyncio.create_task(start_cleanup_task())
            logger.info("✅ 并发控制系统已启动")
            
        except Exception as e:
            logger.error(f"❌ 并发控制系统初始化失败: {e}")
            # 并发控制失败不阻止应用启动，但会记录错误
            logger.warning("⚠️ 并发控制初始化失败，应用将继续运行")
        
        # 2. 条件性初始化 WARP 相关组件（仅代理模式）
        if settings.ENABLE_WARP_PROXY:
            logger.info("🌐 初始化 WARP 代理系统...")
            
            try:
                from app.utils.warp_optimizer import get_warp_optimizer, WARPOptimizationConfig
                from app.utils.proxy_pool import initialize_proxy_pool, shutdown_proxy_pool
                
                # 初始化 WARP 优化器
                warp_opt_config = WARPOptimizationConfig(
                    target_config_count=8,
                    min_config_count=5,
                    max_config_count=8,
                    config_dir=settings.WARP_CONFIG_DIR,
                    account_tier=AccountTier.FREE
                )
                optimizer = get_warp_optimizer(warp_opt_config)
                
                # 初始化 WARP 配置
                init_result = await optimizer.initialize()
                logger.info(f"✅ WARP 配置初始化完成: {init_result}")
                
                # 启动优化循环
                await optimizer.start_optimization_loop()
                logger.info("✅ WARP 优化循环已启动")
                
                # 初始化 WARP 代理池
                await initialize_proxy_pool(
                    config_dir=settings.WARP_CONFIG_DIR,
                    health_check_interval=settings.PROXY_HEALTH_CHECK_INTERVAL
                )
                logger.info("✅ WARP 代理池已初始化")
                
            except Exception as e:
                logger.error(f"❌ WARP 代理系统初始化失败: {e}")
                # 在直链模式下，WARP 失败不应该阻止应用启动
                if not settings.DIRECT_LINK_MODE:
                    raise
                else:
                    logger.warning("⚠️ WARP 初始化失败，继续使用直链模式")
        else:
            logger.info("🔄 跳过 WARP 代理初始化（直链模式）")
        
        # 3. 启动后台任务（条件性）
        try:
            from app.utils.background_tasks import start_background_tasks, stop_background_tasks
            await start_background_tasks()
            logger.info("✅ 后台任务已启动")
        except Exception as e:
            logger.error(f"❌ 后台任务启动失败: {e}")
            # 后台任务失败不应该阻止应用启动
            logger.warning("⚠️ 后台任务启动失败，应用将继续运行")
        
        logger.info("🎉 YTDLP FastAPI 服务启动完成!")
        
        # === 应用运行期间 ===
        yield
        
    except Exception as e:
        logger.error(f"💥 应用启动失败: {e}")
        raise
    
    finally:
        # === 应用关闭 ===
        logger.info("🛑 关闭 YTDLP FastAPI 服务...")
        
        # 1. 停止并发控制清理任务
        if cleanup_task:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("✅ 并发控制任务已停止")
        
        # 2. 停止后台任务
        try:
            from app.utils.background_tasks import stop_background_tasks
            await stop_background_tasks()
            logger.info("✅ 后台任务已停止")
        except Exception as e:
            logger.error(f"❌ 后台任务停止失败: {e}")
        
        # 3. 条件性关闭 WARP 相关组件
        if settings.ENABLE_WARP_PROXY:
            try:
                from app.utils.warp_optimizer import get_warp_optimizer
                from app.utils.proxy_pool import shutdown_proxy_pool
                
                # 停止 WARP 优化循环
                optimizer = get_warp_optimizer()
                if optimizer:
                    await optimizer.stop_optimization_loop()
                    logger.info("✅ WARP 优化循环已停止")
                
                # 关闭代理池
                await shutdown_proxy_pool()
                logger.info("✅ WARP 代理池已关闭")
                
            except Exception as e:
                logger.error(f"❌ WARP 系统关闭失败: {e}")
        
        logger.info("👋 YTDLP FastAPI 服务已完全关闭")

# 解析允许的主机
try:
    allowed_hosts = settings.ALLOWED_HOSTS.split(",")
except Exception as e:
    logger.error(f"❌ 解析 ALLOWED_HOSTS 失败: {e}")
    allowed_hosts = ["*"]  # 失败时的默认值

# 初始化 FastAPI 应用
try:
    app = FastAPI(
        title="YTDLP FastAPI",
        description="高性能 YouTube 视频解析 API - 支持智能并发控制和 WARP 代理优化",
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/" if not bool(settings.DISABLE_DOCS) else None,
        redoc_url="/redoc" if not bool(settings.DISABLE_DOCS) else None,
        openapi_url=None if bool(settings.DISABLE_DOCS) else "/openapi.json"
    )
    
    logger.info("✅ FastAPI 应用初始化成功")
    
except Exception as e:
    logger.error(f"💥 FastAPI 应用初始化失败: {e}")
    raise

# 添加中间件（带错误处理）
try:
    # CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 在生产环境中应该设置具体的域名
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 信任主机中间件
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=allowed_hosts
    )
    
    # 请求追踪中间件
    app.add_middleware(CorrelationIdMiddleware)
    
    # 自定义中间件
    app.add_middleware(ProcessTimeMiddleware)
    app.add_middleware(NodeMiddleware)
    app.add_middleware(RefererCheckMiddleware)
    
    logger.info("✅ 中间件配置完成")
    
except Exception as e:
    logger.error(f"❌ 中间件配置失败: {e}")
    raise

# 包含 API 路由
try:
    app.include_router(router)
    logger.info("✅ API 路由配置完成")
except Exception as e:
    logger.error(f"❌ API 路由配置失败: {e}")
    raise

# 健康检查端点
@app.get("/health", include_in_schema=False)
async def health_check():
    """简单的健康检查端点"""
    return {
        "status": "healthy",
        "service": "YTDLP FastAPI",
        "mode": "direct" if settings.DIRECT_LINK_MODE else "proxy",
        "warp_enabled": bool(settings.ENABLE_WARP_PROXY)
    }

logger.info("🚀 YTDLP FastAPI 应用配置完成，等待启动...")
