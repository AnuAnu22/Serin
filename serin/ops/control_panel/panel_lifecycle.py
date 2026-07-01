"""Server lifecycle, bot state, and WebSocket handler."""
import asyncio
import logging
from datetime import datetime
from typing import Any

import uvicorn

from serin.config.config import config
from serin.logger import logger
from serin.ops.control_panel.server import bot_state, broadcast_log


def init_bot_state(
    discord_client: Any,
    message_manager: Any,
    background_processor: Any,
    passive_monitor: Any,
    message_crawler: Any,
    memory_system: Any,
    voice_listener: Any | None = None,
    tts_engine: Any | None = None,
    voice_manager: Any | None = None
) -> None:
    bot_state['discord_client'] = discord_client
    bot_state['message_manager'] = message_manager
    bot_state['background_processor'] = background_processor
    bot_state['passive_monitor'] = passive_monitor
    bot_state['message_crawler'] = message_crawler
    bot_state['memory_system'] = memory_system
    bot_state['voice_listener'] = voice_listener
    bot_state['tts_engine'] = tts_engine
    bot_state['voice_manager'] = voice_manager
    logger.info(" Control panel state initialized")

async def start_server(app: Any = None, host: str = "127.0.0.1", port: int = 8080) -> None:
    """Start web server with port retry logic"""
    if app is None:
        from serin.ops.control_panel.server import app as _app
        app = _app
    if host != "127.0.0.1" and not config.CONTROL_PANEL_KEY:
        logger.warning("Control panel exposed to network without authentication!")
    max_retries = 5
    current_port = port

    for i in range(max_retries):
        try:
            uvicorn_cfg = uvicorn.Config(
                app,
                host=host,
                port=current_port,
                log_level="info",
                access_log=False
            )
            server = uvicorn.Server(uvicorn_cfg)

            logger.info(f" Control panel starting at http://{host}:{current_port}")
            await server.serve()
            break

        except OSError as e:
            if e.errno == 98:
                logger.warning(f" Port {current_port} is busy, trying {current_port + 1}...")
                current_port += 1
            else:
                raise e
        except SystemExit:
            logger.warning(f" Port {current_port} failed to bind, trying {current_port + 1}...")
            current_port += 1
        except Exception as e:
            if "address already in use" in str(e).lower() or "[errno 98]" in str(e).lower():
                logger.warning(f" Port {current_port} is busy (error: {e}), trying {current_port + 1}...")
                current_port += 1
            else:
                logger.error(f" Failed to start web server: {e}")
                raise e

# ── WebSocket log handler ────────────────────────────────────────────────

class WebSocketLogHandler(logging.Handler):
    """Custom log handler that broadcasts to WebSocket clients"""

    def emit(self, record) -> None:
        try:
            log_entry = {
                'timestamp': datetime.now().isoformat(),
                'level': record.levelname,
                'message': record.getMessage()
            }

            try:
                asyncio.create_task(broadcast_log(log_entry))
            except RuntimeError:
                logger.exception("No event loop for WebSocket log broadcast")
        except Exception:
            logger.exception("WebSocket log handler emit failed")


def register_lifecycle_routes(app):
    """Register lifecycle routes."""
    ws_handler = WebSocketLogHandler()
    ws_handler.setLevel(logging.INFO)
    logger.addHandler(ws_handler)
