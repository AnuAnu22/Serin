"""Entry point — starts the Serin Discord bot."""
import asyncio
from serin.d1_2_gateway_io.discord.bot_pipeline_init import main

if __name__ == "__main__":
    asyncio.run(main())
