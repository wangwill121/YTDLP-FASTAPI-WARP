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
from app.utils.proxy_pool import initialize_proxy_pool, shutdown_proxy_pool
from app.utils.background_tasks import start_background_tasks, stop_background_tasks
from app.utils.concurrency_limiter import get_concurrency_limiter, start_cleanup_task, ConcurrencyConfig, AccountTier
from app.utils.warp_optimizer import get_warp_optimizer, WARPOptimizationConfig
import asyncio
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Lifespan context manager for startup and shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logging.info("启动 YTDLP FastAPI 服务...")
    
    # 初始化并发控制系统
    concurrency_config = ConcurrencyConfig(
        account_tier=AccountTier.FREE,
        max_queue_size=50,
        request_timeout=45.0
    )
    limiter = get_concurrency_limiter(concurrency_config)
    
    # 启动并发控制清理任务
    cleanup_task = asyncio.create_task(start_cleanup_task())
    logging.info("✅ 并发控制系统已启动")
    
    if settings.ENABLE_WARP_PROXY:
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
        logging.info(f"✅ WARP 配置初始化完成: {init_result}")
        
        # 启动优化循环
        await optimizer.start_optimization_loop()
        logging.info("✅ WARP 优化循环已启动")
        
        # 初始化 WARP 代理池
        await initialize_proxy_pool(
            config_dir=settings.WARP_CONFIG_DIR,
            health_check_interval=settings.PROXY_HEALTH_CHECK_INTERVAL
        )
        logging.info("✅ WARP 代理池已初始化")
    
    # 启动其他后台任务
    await start_background_tasks()
    
    yield
    
    # Shutdown
    logging.info("关闭 YTDLP FastAPI 服务...")
    
    # 停止清理任务
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    
    # 停止后台任务
    await stop_background_tasks()
    
    if settings.ENABLE_WARP_PROXY:
        # 停止 WARP 优化循环
        optimizer = get_warp_optimizer()
        await optimizer.stop_optimization_loop()
        logging.info("✅ WARP 优化循环已停止")
        
        # 关闭代理池
        await shutdown_proxy_pool()
        logging.info("✅ WARP 代理池已关闭")

# Parse the allowed hosts from the settings
allowed_hosts = settings.ALLOWED_HOSTS.split(",")

# Initialize the FastAPI application
app = FastAPI(
    title="YTDLP FastAPI",
    description="高性能 YouTube 视频解析 API - 支持智能并发控制和 WARP 代理优化",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/" if not bool(settings.DISABLE_DOCS) else None,
    redoc_url="/redoc" if not bool(settings.DISABLE_DOCS) else None,
    openapi_url=None if bool(settings.DISABLE_DOCS) else "/openapi.json"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应该设置具体的域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add trusted host middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=allowed_hosts
)

# Add correlation ID middleware for request tracing
app.add_middleware(CorrelationIdMiddleware)

# Add custom middlewares
app.add_middleware(ProcessTimeMiddleware)
app.add_middleware(NodeMiddleware)
app.add_middleware(RefererCheckMiddleware)

# Include the API routes
app.include_router(router)


@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger = logging.getLogger(__name__)
    logger.info("🚀 YTDLP FastAPI 启动中...")
    logger.info(f"📊 直链模式: {'启用' if settings.DIRECT_LINK_MODE else '禁用'}")
    logger.info(f"🔐 允许的域名: {settings.ALLOWED_HOSTS}")
    logger.info(f"⚡ 并发控制: 已启用 (Cloudflare 免费账户优化)")
    logger.info(f"🔧 WARP 优化: {'已启用' if settings.ENABLE_WARP_PROXY else '已禁用'}")
    logger.info("✅ 应用启动完成")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    logger = logging.getLogger(__name__)
    logger.info("🛑 YTDLP FastAPI 正在关闭...")
    logger.info("✅ 应用关闭完成")
