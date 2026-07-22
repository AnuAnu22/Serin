"""Main async entry point with database protection.

Extracted from the former ``bot_pipeline_init.py`` so that module stays under
the 500-line ceiling (Rule 2: a file over 500 lines becomes a folder). The
package ``__init__`` re-exports ``main`` so existing import paths keep working.
"""

from __future__ import annotations

import asyncio
from typing import cast

import aiohttp
import discord

import serin.d1_1_pipeline_flow.d2_5_flow_think.d3_3_response_generator
from serin.d1_2_gateway_io.d2_1_io_discord import (
    d3_4_event_handlers,  # noqa: F401  registers event handlers
)
from serin.d1_2_gateway_io.d2_1_io_discord.d3_2_discord_bot import client
from serin.d1_2_gateway_io.d2_4_io_di import get_logger
from serin.d1_3_state_core.d2_1_db_protect import (
    DatabaseRecoveryError,
    DatabaseValidationError,
)
from serin.d1_4_config_base.d2_1_base_config import config


async def main() -> None:
    """Main async function with database protection"""
    try:
        get_logger().info("=" * 60)
        get_logger().info("Serin Discord Bot")
        get_logger().info("WITH DATABASE PROTECTION")
        get_logger().info("=" * 60)

        if config.DEBUG_MODE:
            get_logger().info("Debug mode enabled - verbose logging active")

        get_logger().info("Configuration:")
        get_logger().info(f"   Trace messages: {config.TRACE_MESSAGES}")
        get_logger().info(f"   Response channels: {len(config.ALLOWED_CHANNEL_IDS)}")
        get_logger().info("   Monitoring: ALL channels (passive learning)")
        get_logger().info(f"   Maintenance interval: {config.MAINTENANCE_INTERVAL_HOURS}h")
        get_logger().info("   Cross-server memory: ENABLED")
        get_logger().info(f"   Voice tracking: {config.ENABLE_VOICE}")
        get_logger().info("   Multi-model: ENABLED (via factory)")
        get_logger().info("   Temporal awareness: ENABLED")
        get_logger().info("   Correction learning: ENABLED")
        get_logger().info("   Database Protection: ENABLED")
        get_logger().info("=" * 60)

        # Set up discord client reference
        serin.d1_1_pipeline_flow.d2_5_flow_think.d3_3_response_generator.discord_client = client
        get_logger().debug("Discord client reference set")

        max_retries = 5
        retry_count = 0

        while retry_count < max_retries:
            try:
                async with client:
                    # Start maintenance task (only here, not in on_ready)
                    get_logger().info("Starting maintenance task...")
                    asyncio.create_task(d3_4_event_handlers.run_maintenance())
                    get_logger().debug("Maintenance task scheduled")

                    # Start Discord client with retry
                    get_logger().info(f"Connecting to Discord (Attempt {retry_count + 1}/{max_retries})...")
                    await client.start(cast(str, config.DISCORD_TOKEN))
                    break

            except (aiohttp.ClientError, discord.ConnectionClosed, discord.GatewayNotFound) as e:
                retry_count += 1
                if retry_count < max_retries:
                    wait_time = min(30, 2 ** retry_count)
                    get_logger().warning(f"Connection attempt {retry_count} failed: {e}")
                    get_logger().info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    get_logger().error(f"Failed to connect after {max_retries} attempts: {e}")
                    raise

    except KeyboardInterrupt:
        get_logger().info("Received keyboard interrupt (Ctrl+C)")

    except DatabaseValidationError as e:
        get_logger().error(f"Database validation failed: {e}")
        get_logger().error("Manual intervention required")

    except DatabaseRecoveryError as e:
        get_logger().error(f"Database recovery failed: {e}")
        get_logger().error("Try restoring from backup manually")

    except Exception as e:
        get_logger().exception(f"Fatal error in main: {e}")
    finally:
        get_logger().info("Bot shutdown complete")
        if not client.is_closed():
            await client.close()
