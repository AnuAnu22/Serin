from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import WebSocket

from serin.d1_4_config_base.d2_3_logger import logger
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_7_state.d5_1_state_access import (
    _ws_lock,
    active_websockets,
    app,
    bot_state,
    get_gpu_vram_usage,
)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    async with _ws_lock:
        active_websockets.append(websocket)
        count = len(active_websockets)
    logger.info("WebSocket connected (total: %d)", count)
    try:
        await _send_heartbeat(websocket)
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
            except TimeoutError:
                pass
            except Exception:
                logger.debug("WebSocket receive failed, disconnecting")
                break
            try:
                if websocket.client_state.value != 1:
                    break
            except Exception:
                logger.debug("WebSocket client_state check failed")
                break
            await _send_heartbeat(websocket)
    except Exception as e:
        logger.debug("WebSocket error: %s", e)
    finally:
        async with _ws_lock:
            if websocket in active_websockets:
                active_websockets.remove(websocket)
            remaining = len(active_websockets)
        try:
            await websocket.close()
        except Exception:
            logger.debug("WebSocket close error")
        logger.info("WebSocket disconnected (remaining: %d)", remaining)


async def _send_heartbeat(websocket: WebSocket) -> None:
    try:
        client = bot_state.get("discord_client")
        latency = int(client.latency * 1000) if client and hasattr(client, "latency") else 0
        manager = bot_state.get("message_manager")
        brain_state = "ONLINE"
        if manager and hasattr(manager, "current_state"):
            brain_state = manager.current_state.get("status", "ONLINE")
        gpu = await get_gpu_vram_usage()
        await websocket.send_json({
            "type": "heartbeat",
            "latency": latency,
            "gpu": gpu,
            "brain_state": brain_state,
            "ts": time.time(),
        })
    except Exception as e:
        logger.debug("Error sending heartbeat: %s", e)
        raise


async def broadcast_log(log_entry: dict[str, Any]) -> None:
    async with _ws_lock:
        to_remove: list[WebSocket] = []
        for ws in active_websockets:
            try:
                if ws.client_state.value != 1:
                    to_remove.append(ws)
                    continue
                await ws.send_json({
                    "type": "log",
                    "msg": log_entry.get("message", str(log_entry)),
                    "level": log_entry.get("level", "INFO"),
                    "ts": time.time(),
                })
            except Exception:
                logger.debug("Broadcast log send failed, removing WS")
                to_remove.append(ws)
        for ws in to_remove:
            if ws in active_websockets:
                active_websockets.remove(ws)


async def broadcast_event(event_type: str, data: dict[str, Any]) -> None:
    async with _ws_lock:
        to_remove: list[WebSocket] = []
        for ws in active_websockets:
            try:
                if ws.client_state.value != 1:
                    to_remove.append(ws)
                    continue
                await ws.send_json({"type": event_type, "data": data, "ts": time.time()})
            except Exception:
                logger.debug("Broadcast event send failed, removing WS")
                to_remove.append(ws)
        for ws in to_remove:
            if ws in active_websockets:
                active_websockets.remove(ws)
