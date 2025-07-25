from fastapi import APIRouter

from . import video

router = APIRouter(prefix="/v1")

router.include_router(video.router)
