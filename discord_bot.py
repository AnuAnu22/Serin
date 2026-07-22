"""Entry point — starts the Serin Discord bot."""
import asyncio
from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import main

if __name__ == "__main__":
    asyncio.run(main())
