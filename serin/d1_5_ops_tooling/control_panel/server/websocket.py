"""WebSocket live updates and log/event broadcast for the control panel."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket

from serin.d1_3_state_core.logger import logger
from serin.d1_5_ops_tooling.control_panel.server.state import (
    active_websockets,
    app,
    bot_state,
    get_gpu_vram_usage,
)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> Any:
    """WebSocket for real-time log streaming and stats updates"""
    await websocket.accept()
    active_websockets.append(websocket)
    logger.info(f" WebSocket connected (total: {len(active_websockets)})")

    try:
        # Send initial stats immediately
        try:
            client = bot_state['discord_client']
            latency = int(client.latency * 1000) if not client else 0
            manager = bot_state['message_manager']
            brain_state = 'ONLINE'
            if manager and hasattr(manager, 'current_state'):
                brain_state = manager.current_state.get('status', 'ONLINE')
            gpu = await get_gpu_vram_usage()

            await websocket.send_json({
                "type": "heartbeat",
                "latency": latency,
                "gpu": gpu,
                "brain_state": brain_state
            })
        except Exception as e:
            logger.error(f"Error sending initial stats: {e}")
            raise

        while True:
            # Wait for messages or timeout
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
            except TimeoutError:
                pass
            except Exception:
                break

            if not websocket.client_state.value == 1:
                break

            # Send Heartbeat
            try:
                client = bot_state['discord_client']
                latency = int(client.latency * 1000) if client else 0
                manager = bot_state['message_manager']
                brain_state = 'ONLINE'
                if manager and hasattr(manager, 'current_state'):
                    brain_state = manager.current_state.get('status', 'ONLINE')
                gpu = await get_gpu_vram_usage()

                await websocket.send_json({
                    "type": "heartbeat",
                    "latency": latency,
                    "gpu": gpu,
                    "brain_state": brain_state
                })

            except Exception as e:
                logger.debug(f"Error sending heartbeat: {e}")
                break

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Cleanup
        if websocket in active_websockets:
            active_websockets.remove(websocket)
        try:
            await websocket.close()
        except Exception:
            logger.exception("Failed to close WebSocket cleanly")
        logger.info(f"WebSocket disconnected (remaining: {len(active_websockets)})")


async def broadcast_log(log_entry: dict[str, Any]) -> None:
    """Broadcast log entry to all connected WebSockets"""
    to_remove = []

    for ws in active_websockets:
        try:
            # Check if connection is still open
            if ws.client_state.value != 1:
                to_remove.append(ws)
                continue

            await ws.send_json({
                'type': 'log',
                'msg': log_entry.get('message', str(log_entry))
            })
        except Exception:
            to_remove.append(ws)

    # Remove disconnected
    for ws in to_remove:
        if ws in active_websockets:
            active_websockets.remove(ws)


async def broadcast_event(event_type: str, data: dict[str, Any]) -> None:
    """Broadcast event to all connected WebSockets"""
    to_remove = []

    for ws in active_websockets:
        try:
            # Check if connection is still open
            if ws.client_state.value != 1:
                to_remove.append(ws)
                continue

            # Pass through decision events directly
            if event_type == 'decision':
                 await ws.send_json(data)
            else:
                await ws.send_json({
                    'type': event_type,
                    'data': data
                })
        except Exception:
            to_remove.append(ws)

    for ws in to_remove:
        if ws in active_websockets:
            active_websockets.remove(ws)
