"""
GameOver Movie Hub — 24/7 Web Server & Keep-Alive Dashboard
Listens on port 7860 (Hugging Face default) or $PORT.
Provides an HTML status dashboard, /health & /ping endpoints,
and a self-ping task to prevent Hugging Face Spaces from idling/sleeping.
"""

import os
import time
import asyncio
import psutil
from aiohttp import web
from config import Config

_START_TIME = time.time()


async def handle_home(request):
    uptime_sec = int(time.time() - _START_TIME)
    hours = uptime_sec // 3600
    mins = (uptime_sec % 3600) // 60
    secs = uptime_sec % 60
    uptime_str = f"{hours}h {mins}m {secs}s"

    try:
        cpu_usage = psutil.cpu_percent(interval=None)
        ram_mb = psutil.Process().memory_info().rss / (1024 * 1024)
    except Exception:
        cpu_usage = 0.0
        ram_mb = 0.0

    try:
        from core.player import stream_manager
        active_streams = len(stream_manager.active_calls) if hasattr(stream_manager, "active_calls") else 0
    except Exception:
        active_streams = 0

    port_val = os.getenv("PORT", "7860")
    bot_user = f"@{Config.BOT_USERNAME}" if Config.BOT_USERNAME else "@Gameovermovie_bot"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GᴀᴍᴇOᴠᴇʀ Mᴏᴠɪᴇ Hᴜʙ — Status</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; font-family: 'Outfit', sans-serif; }}
        body {{ background: #07090e; color: #e2e8f0; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px; }}
        .card {{ background: rgba(18, 24, 38, 0.85); backdrop-filter: blur(20px); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 28px; padding: 42px 36px; max-width: 520px; width: 100%; box-shadow: 0 25px 60px rgba(0,0,0,0.65); text-align: center; }}
        .badge {{ display: inline-flex; align-items: center; gap: 8px; background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.4); color: #10b981; padding: 7px 18px; border-radius: 50px; font-weight: 600; font-size: 0.88rem; margin-bottom: 24px; letter-spacing: 0.5px; }}
        .dot {{ width: 10px; height: 10px; background: #10b981; border-radius: 50%; box-shadow: 0 0 14px #10b981; animation: pulse 1.8s infinite; }}
        @keyframes pulse {{ 0%, 100% {{ opacity: 1; transform: scale(1); }} 50% {{ opacity: 0.4; transform: scale(1.25); }} }}
        h1 {{ font-size: 1.9rem; font-weight: 700; color: #ffffff; margin-bottom: 6px; letter-spacing: -0.5px; }}
        p.subtitle {{ color: #94a3b8; font-size: 0.95rem; margin-bottom: 28px; }}
        .grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; margin-bottom: 24px; }}
        .stat {{ background: rgba(10, 14, 23, 0.75); border: 1px solid rgba(255, 255, 255, 0.05); padding: 16px; border-radius: 16px; text-align: left; }}
        .stat-label {{ color: #64748b; font-size: 0.72rem; text-transform: uppercase; font-weight: 600; letter-spacing: 0.6px; margin-bottom: 4px; }}
        .stat-value {{ color: #f8fafc; font-size: 1.15rem; font-weight: 700; }}
        .full {{ grid-column: span 2; }}
        .footer {{ font-size: 0.8rem; color: #475569; margin-top: 16px; }}
        a {{ color: #38bdf8; text-decoration: none; font-weight: 600; }}
        a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="badge"><div class="dot"></div> 24/7 SERVER ONLINE</div>
        <h1>GᴀᴍᴇOᴠᴇʀ Mᴏᴠɪᴇ Hᴜʙ</h1>
        <p class="subtitle">Telegram Group Video & Movie Stream Engine</p>
        <div class="grid">
            <div class="stat"><div class="stat-label">Bot Handle</div><div class="stat-value"><a href="https://t.me/{bot_user.replace('@', '')}" target="_blank">{bot_user}</a></div></div>
            <div class="stat"><div class="stat-label">System Uptime</div><div class="stat-value">{uptime_str}</div></div>
            <div class="stat"><div class="stat-label">Active Streams</div><div class="stat-value">{active_streams} Calls</div></div>
            <div class="stat"><div class="stat-label">VOD Engine</div><div class="stat-value" style="color: #38bdf8; font-size: 0.95rem;">MovieBox API</div></div>
            <div class="stat"><div class="stat-label">CPU Load</div><div class="stat-value">{cpu_usage}%</div></div>
            <div class="stat"><div class="stat-label">RAM Usage</div><div class="stat-value">{ram_mb:.1f} MB</div></div>
        </div>
        <div class="footer">Hugging Face Space Keep-Alive Active • Port {port_val}</div>
    </div>
</body>
</html>"""
    return web.Response(text=html, content_type="text/html")


async def handle_health(request):
    uptime_sec = int(time.time() - _START_TIME)
    try:
        from core.player import stream_manager
        active_streams = len(stream_manager.active_calls) if hasattr(stream_manager, "active_calls") else 0
    except Exception:
        active_streams = 0

    return web.json_response({
        "status": "online",
        "service": "GameOver Movie Hub",
        "uptime": uptime_sec,
        "bot": Config.BOT_USERNAME or "Gameovermovie_bot",
        "active_streams": active_streams
    })


async def start_web_server():
    """Starts the 24/7 web server and self-ping background task."""
    try:
        app = web.Application()
        app.router.add_get("/", handle_home)
        app.router.add_get("/health", handle_health)
        app.router.add_get("/ping", handle_health)

        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.getenv("PORT", "7860"))
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        print(f"[WebServer]  24/7 Dashboard running on http://0.0.0.0:{port}")

        # Self-ping task to prevent cloud/container sleep
        async def _self_ping_loop():
            await asyncio.sleep(20)
            import aiohttp
            ping_url = f"http://127.0.0.1:{port}/health"
            while True:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(ping_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                            pass
                except Exception:
                    pass
                await asyncio.sleep(240)  # Ping every 4 minutes

        asyncio.create_task(_self_ping_loop())
        return runner
    except Exception as e:
        print(f"[WebServer]  Server start note: {e}")
        return None
