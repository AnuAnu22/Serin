"""Entry point — starts the Serin hot reloader."""
import asyncio
from serin.d1_5_ops_tooling.d2_3_hot_reloader import main

if __name__ == "__main__":
    asyncio.run(main())
