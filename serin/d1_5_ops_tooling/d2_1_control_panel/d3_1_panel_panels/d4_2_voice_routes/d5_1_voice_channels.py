from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from serin.d1_3_state_core.d2_5_core_logger import logger
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_1_state_access import (
    VoiceChannelControl,
    bot_state,
    make_json_safe,
)
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_5_server_websocket import (
    broadcast_event,
)


def register_voice_channel_routes(app: FastAPI) -> None:

    @app.get("/api/voice/channels")
    async def get_voice_channels() -> Any:
        client = bot_state.get("discord_client")
        if not client:
            return {"channels": []}
        try:
            channels = []
            for guild in client.guilds:
                for vc in guild.voice_channels:
                    channels.append({
                        "guild_id": str(guild.id),
                        "guild_name": guild.name,
                        "channel_id": str(vc.id),
                        "channel_name": vc.name,
                        "members": len(vc.members),
                    })
            return {"channels": channels}
        except Exception as e:
            return {"error": str(e), "channels": []}

    @app.post("/api/voice/join")
    async def join_voice_channel(control: VoiceChannelControl) -> Any:
        voice_listener = bot_state.get("voice_listener")
        if not voice_listener:
            return {"success": False, "error": "Voice listener not initialized"}
        try:
            success = await voice_listener.join_channel(
                int(control.guild_id), int(control.channel_id)
            )
            if success:
                logger.info("Joined voice channel: %s", control.channel_id)
                await broadcast_event("voice_joined", {
                    "guild_id": control.guild_id,
                    "channel_id": control.channel_id,
                })
            return {"success": success}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.post("/api/voice/leave")
    async def leave_voice_channel(control: VoiceChannelControl) -> Any:
        voice_listener = bot_state.get("voice_listener")
        if not voice_listener:
            return {"success": False, "error": "Voice listener not initialized"}
        try:
            success = await voice_listener.leave_channel(int(control.guild_id))
            if success:
                await broadcast_event("voice_left", {"guild_id": control.guild_id})
            return {"success": success}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/voice/status")
    async def get_voice_status() -> Any:
        voice_listener = bot_state.get("voice_listener")
        if not voice_listener:
            return {"connected": False}
        try:
            return make_json_safe(voice_listener.get_status())
        except Exception as e:
            return {"error": str(e)}
