def register_lifecycle_routes(app):
    """Register lifecycle routes."""
from datetime import datetime
from typing import Any, Optional
    """Server lifecycle, bot state, and WebSocket handler."""
    def init_bot_state(
        discord_client: Any,
        message_manager: Any,
        background_processor: Any,
        passive_monitor: Any,
        message_crawler: Any,
        memory_system: Any,
        voice_listener: Optional[Any] = None,
        tts_engine: Optional[Any] = None,
        voice_manager: Optional[Any] = None
    ) -> None:
        """Initialize bot state for control panel"""
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


    async def start_server(host: str = "127.0.0.1", port: int = 8080) -> Any:
        """Start web server with port retry logic"""
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
                break  # If successful (or clean exit), stop retrying
            
            except OSError as e:
                if e.errno == 98:  # Address already in use
                    logger.warning(f" Port {current_port} is busy, trying {current_port + 1}...")
                    current_port += 1
                else:
                    raise e
            except SystemExit:
                 # Uvicorn raises SystemExit on startup failure
                 logger.warning(f" Port {current_port} failed to bind, trying {current_port + 1}...")
                 current_port += 1
            except Exception as e:
                # Catch generic startup errors that might be port related
                if "address already in use" in str(e).lower() or "[errno 98]" in str(e).lower():
                    logger.warning(f" Port {current_port} is busy (error: {e}), trying {current_port + 1}...")
                    current_port += 1
                else:
                    logger.error(f" Failed to start web server: {e}")
                    raise e


    # ============================================================================
    # HELPER: Inject custom logger handler for WebSocket streaming
    # ============================================================================

    import logging

    class WebSocketLogHandler(logging.Handler):
        """Custom log handler that broadcasts to WebSocket clients"""
    
        def emit(self, record) -> None:
            try:
                log_entry = {
                    'timestamp': datetime.now().isoformat(),
                    'level': record.levelname,
                    'message': record.getMessage()
                }
            
                # Schedule broadcast in event loop safely
                try:
                    loop = asyncio.get_running_loop()
                    asyncio.create_task(broadcast_log(log_entry))
                except RuntimeError:
                    pass  # Not in an async context, skip broadcast
            except Exception:
                pass  # Silently fail to avoid recursion

    # Add handler to logger
    ws_handler = WebSocketLogHandler()
    ws_handler.setLevel(logging.INFO)
    logger.addHandler(ws_handler)
