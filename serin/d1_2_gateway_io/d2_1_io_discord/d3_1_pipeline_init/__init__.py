"""
MessagePipeline and behavior manager initialization.

This package is the folder form of the former ``bot_pipeline_init.py`` (Rule 2:
a file over 500 lines becomes a folder). ``on_ready``, ``on_message`` and the
module-level subsystem globals stay here so their ``global`` bindings resolve in
the package namespace; ``main`` lives in ``main_entry.py`` and is re-exported.
"""
# --- Imports ---
from __future__ import annotations

from typing import Any

import discord

from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init.d4_1_pipeline_initializer import (
    PipelineInitializer,
)
from serin.d1_2_gateway_io.d2_1_io_discord.d3_2_discord_bot import (
    background_processor,
    client,
    db_protector,
    message_crawler,
    passive_monitor,
    stats,
)
from serin.d1_2_gateway_io.d2_1_io_discord.d3_3_command_handlers import (
    handle_help_command,
    handle_profile_command,
    handle_stats_command,
)
from serin.d1_2_gateway_io.d2_4_io_di import get_logger
from serin.d1_4_config_base.d2_1_base_config import config
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server import bot_state

from .d4_1_main_entry import main

# --- Types ---
# (none)

# --- Constants ---
__all__ = [
    "background_processor",
    "db_protector",
    "main",
    "message_manager",
    "message_crawler",
    "on_message",
    "on_ready",
    "passive_monitor",
]

# --- Entry ---
_initializer: PipelineInitializer | None = None

# Module-level attributes for backward compatibility with event_handlers
message_manager: Any | None = None
voice_behavior_manager: Any | None = None
voice_listener: Any | None = None


# --- Core ---
@client.event
async def on_ready() -> None:
    """Bot connected to Discord — initialize all subsystems."""
    global _initializer, message_manager, voice_behavior_manager, voice_listener
    _initializer = PipelineInitializer(client, bot_state)
    await _initializer.initialize()
    message_manager = _initializer.message_manager
    voice_behavior_manager = _initializer.voice_behavior_manager
    voice_listener = _initializer.voice_listener


@client.event
async def on_message(message: discord.Message) -> None:
    """Handle incoming messages from ALL channels"""
    global stats

    try:
        stats['messages_received'] += 1

        # Filter 1: Ignore bot's own messages
        if message.author == client.user:
            return

        # Filter 2: Only text channels
        if not isinstance(message.channel, discord.TextChannel):
            return

        # Filter 3: Ignore empty messages (unless they have attachments)
        content = message.content.strip()
        if not content and not message.attachments:
            return

        # Check if in allowed channel
        is_allowed_channel = message.channel.id in config.ALLOWED_CHANNEL_IDS

        if config.TRACE_MESSAGES:
            channel_type = "ACTIVE" if is_allowed_channel else "PASSIVE"
            get_logger().debug(
                f"[{channel_type}] Message #{stats['messages_received']}: "
                f"'{content[:50]}...' from {message.author.display_name} "
                f"in #{message.channel.name}"
            )

        # === PASSIVE MONITORING (ALL CHANNELS) ===
        if _initializer and _initializer.passive_monitor:
            await _initializer.passive_monitor.process_message(message, is_allowed_channel)

        if is_allowed_channel:
            stats['messages_processed'] += 1
        else:
            stats['passive_messages'] += 1
            return

        # === HANDLE COMMANDS ===
        if _initializer and _initializer.message_manager:
            if await handle_profile_command(message, _initializer.message_manager, stats):
                return
            if await handle_stats_command(message, _initializer.message_manager, _initializer.background_processor, _initializer.passive_monitor, _initializer.message_crawler, stats):
                return
        if await handle_help_command(message, stats):
            return

        # === PROCESS REGULAR MESSAGE ===
        get_logger().debug(f"Processing message from {message.author.display_name}")

        if _initializer is None or _initializer.message_manager is None:
            get_logger().error("MessageManager not initialized!")
            stats['errors'] += 1
            return

        # Pass to message manager for response generation
        await _initializer.message_manager.process_message(message)

    except Exception as e:
        stats['errors'] += 1
        get_logger().exception(f"Error in on_message: {e}")

# --- Helpers ---
# (none)

# --- Errors ---
# (none)


if __name__ == "__main__":
    try:
        import asyncio
        asyncio.run(main())
    except KeyboardInterrupt:
        get_logger().info("Received shutdown signal")
    except Exception as e:
        get_logger().exception(f"Fatal error: {e}")
