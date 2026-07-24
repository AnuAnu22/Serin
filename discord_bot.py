"""Unified entry point — auto-starts Qdrant, then runs the hot-reloader
which spawns and manages the Serin Discord bot subprocess (auto-restart on
file changes)."""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv

from serin.d1_5_ops_tooling.d2_3_hot_reloader import main as hot_reloader_main

PROJECT_DIR = Path(__file__).resolve().parent
ENV_FILE = PROJECT_DIR / ".env"

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)


# ── Qdrant auto-start ──────────────────────────────────────────────


def _docker_available() -> bool:
    try:
        subprocess.run(
            ["docker", "info"],
            capture_output=True,
            check=False,
            timeout=10,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _qdrant_running(port: int = 6333) -> bool:
    import urllib.request

    try:
        urllib.request.urlopen(f"http://localhost:{port}/health", timeout=2)
        return True
    except Exception:
        return False


async def auto_start_qdrant() -> None:
    """Start Qdrant Docker container if QDRANT_USE_DOCKER=true."""
    if os.getenv("QDRANT_USE_DOCKER", "true").lower() != "true":
        print("[BOOT] Qdrant auto-start disabled (QDRANT_USE_DOCKER != true)")
        return

    port = int(os.getenv("QDRANT_PORT", "6333"))
    container = os.getenv("QDRANT_DOCKER_CONTAINER_NAME", "serin-qdrant")
    image = os.getenv("QDRANT_DOCKER_IMAGE", "qdrant/qdrant:latest")

    if _qdrant_running(port):
        print(f"[BOOT] Qdrant already running on port {port}")
        return

    if not _docker_available():
        print("[BOOT] Docker not available — skipping Qdrant auto-start")
        return

    result = subprocess.run(
        ["docker", "ps", "-a", "--filter", f"name=^{container}$", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    existing = result.stdout.strip()

    if existing:
        print(f"[BOOT] Starting existing Qdrant container: {container}")
        subprocess.run(["docker", "start", container], check=True, timeout=30)
    else:
        print(f"[BOOT] Creating new Qdrant container: {container}")
        subprocess.run(
            [
                "docker", "run", "-d",
                "--name", container,
                "--restart", "unless-stopped",
                "-p", f"{port}:6333",
                "-p", "6334:6334",
                image,
            ],
            check=True,
            timeout=60,
        )

    print(f"[BOOT] Waiting for Qdrant on port {port}...")
    for _ in range(60):
        if _qdrant_running(port):
            print("[BOOT] Qdrant is ready!")
            return
        await asyncio.sleep(1)

    print("[BOOT] Qdrant not ready within 60s — continuing anyway")


async def main() -> None:
    await auto_start_qdrant()
    await hot_reloader_main()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[BOOT] Shutting down")
