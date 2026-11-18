import os
import sys
import time
import logging
from aiohttp import web

logger = logging.getLogger(__name__)
log = logger

routes = web.RouteTableDef()


@routes.get("/", allow_head=True)
@routes.get("/health", allow_head=True)
@routes.get("/ping", allow_head=True)
async def health_check_handler(request):
    """
    Bulletproof 200 OK health diagnostic endpoint.
    Reports real-time RAM usage via psutil and process uptime for Render monitoring.
    """
    try:
        import psutil
        process = psutil.Process(os.getpid())
        ram_bytes = process.memory_info().rss
        ram_mb = round(ram_bytes / (1024 * 1024), 2)
        ram_percent = round(process.memory_percent(), 2)
    except Exception:
        ram_mb = 0.0
        ram_percent = 0.0

    uptime_sec = 0.0
    try:
        from bot import BOT_START_TIME
        uptime_sec = round(time.time() - BOT_START_TIME, 2)
    except Exception:
        app_start = getattr(request.app, "_start_time", time.time())
        uptime_sec = round(time.time() - app_start, 2)

    return web.json_response({
        "status": "ok",
        "bot": "NeX 4GB Rename Bot",
        "developer": "@Nex_bots",
        "uptime_seconds": uptime_sec,
        "ram_usage_mb": ram_mb,
        "ram_percent": ram_percent
    }, status=200)


async def web_server():
    web_app = web.Application(client_max_size=30000000)
    web_app._start_time = time.time()
    web_app.add_routes(routes)
    return web_app
