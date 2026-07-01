"""Serin Discord Bot — root entry point.

Usage: python -m serin
"""
import asyncio
from serin.gateway.discord.bot import *  # noqa: sets up client, handlers, globals
from serin.gateway.discord.bot_pipeline_init import main

if __name__ == "__main__":
    asyncio.run(main())
