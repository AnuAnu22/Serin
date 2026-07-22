"""WebSocket live updates and log/event broadcast for the control panel."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from serin.d1_3_state_core.d2_5_core_logger import logger
from serin.d1_4_config_base.d2_1_base_config import config
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_3_server_state import (
    _key_is_valid,
    active_websockets,
    active_websockets_lock,
    app,
    bot_state,
    get_gpu_vram_usage,
)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> Any:
    """WebSocket for real-time log streaming and stats updates.

    The HTTP auth middleware in ``state.py`` does not run for the WebSocket
    upgrade handshake, so the same X-API-Key check is repeated here
    explicitly — otherwise the WS endpoint would be the one unauthenticated
    door into a panel that's supposed to be fully key-gated.
    """
    if config.CONTROL_PANEL_KEY:
        api_key = websocket.headers.get("x-api-key", "")
        if not _key_is_valid(api_key):
            await websocket.close(code=4401)
            return

    await websocket.accept()
    async with active_websockets_lock:
        active_websockets.append(websocket)
        connected_count = len(active_websockets)
    logger.info(f" WebSocket connected (total: {connected_count})")

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

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        async with active_websockets_lock:
            if websocket in active_websockets:
                active_websockets.remove(websocket)
            remaining = len(active_websockets)
        try:
            await websocket.close()
        except Exception:
            # Already closed by the client — expected, not an error.
            pass
        logger.info(f"WebSocket disconnected (remaining: {remaining})")


async def broadcast_log(log_entry: dict[str, Any]) -> None:
    """Broadcast log entry to all connected WebSockets."""
    await _broadcast(lambda ws: ws.send_json({
        'type': 'log',
        'msg': log_entry.get('message', str(log_entry)),
    }))


async def broadcast_event(event_type: str, data: dict[str, Any]) -> None:
    """Broadcast event to all connected WebSockets."""
    payload = data if event_type == 'decision' else {'type': event_type, 'data': data}
    await _broadcast(lambda ws: ws.send_json(payload))


async def _broadcast(send: Any) -> None:
    """Send to every live socket under the lock, snapshotting the list first
    so a socket connecting or disconnecting mid-broadcast can't corrupt the
    iteration. Dead sockets found along the way are pruned in the same
    locked section that computed the snapshot, so pruning can't race a
    concurrent append/remove either.
    """
    async with active_websockets_lock:
        snapshot = list(active_websockets)

    dead: list[WebSocket] = []
    for ws in snapshot:
        try:
            if ws.client_state.value != 1:
                dead.append(ws)
                continue
            await send(ws)
        except Exception:
            dead.append(ws)

    if dead:
        async with active_websockets_lock:
            for ws in dead:
                if ws in active_websockets:
                    active_websockets.remove(ws)
