"""Qdrant Docker connection management — retry + auto-start.
Extracted from store.py.
"""
import time as time_mod
from typing import Any

import docker

from serin.config.config import config
from serin.state.logger import logger

# Qdrant imports
try:
    from qdrant_client import QdrantClient
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    logger.warning("Qdrant not available - falling back to mock implementation")


def connect_with_retry(host: str, port: int, max_attempts: int = 3) -> Any | None:
    """Try connecting to Qdrant, then fall back to Docker auto-start if configured."""
    if not QDRANT_AVAILABLE:
        logger.warning("Qdrant not available - cannot connect")
        return None

    for attempt in range(max_attempts):
        try:
            client = QdrantClient(host=host, port=port, timeout=5.0)
            client.get_collections()
            logger.info(f" Qdrant client connected to {host}:{port}")
            return client
        except Exception as e:
            if attempt < max_attempts - 1:
                logger.warning(f" Qdrant connection failed (attempt {attempt+1}/{max_attempts}): {e}. Retrying...")
                time_mod.sleep(2)
            else:
                logger.error(f" Failed to connect to Qdrant after {max_attempts} attempts: {e}")

    if config.QDRANT_USE_DOCKER or host in ("localhost", "127.0.0.1"):
        logger.info(" Attempting Qdrant Docker auto-start...")
        return ensure_qdrant_docker(host, port)
    return None


def find_qdrant_container() -> str | None:
    """Find any existing Qdrant container (by configured name or image)."""
    try:
        client = docker.from_env()
        containers = client.containers.list(
            all=True,
            filters={"name": config.QDRANT_DOCKER_CONTAINER_NAME},
        )
        for c in containers:
            if config.QDRANT_DOCKER_CONTAINER_NAME in c.name:
                return config.QDRANT_DOCKER_CONTAINER_NAME
    except Exception:
        logger.exception("Failed to find Qdrant container by name")

    try:
        client = docker.from_env()
        containers = client.containers.list(
            all=True,
            filters={"ancestor": config.QDRANT_DOCKER_IMAGE},
        )
        if containers:
            return containers[0].name
    except Exception:
        logger.exception("Failed to find Qdrant container by image")

    try:
        client = docker.from_env()
        containers = client.containers.list(all=True)
        for c in containers:
            image_tags = c.image.tags if hasattr(c.image, 'tags') else []
            if any("qdrant" in tag.lower() for tag in image_tags):
                return c.name
    except Exception:
        logger.exception("Failed to list Docker containers for Qdrant search")

    return None


def ensure_qdrant_docker(host: str, port: int) -> Any | None:
    """Auto-start Qdrant via Docker if container exists or can be created."""
    if not QDRANT_AVAILABLE:
        return None

    container_name = find_qdrant_container()
    image = config.QDRANT_DOCKER_IMAGE

    try:
        client = docker.from_env()
        if container_name:
            logger.info(f" Starting Qdrant container '{container_name}'...")
            container = client.containers.get(container_name)
            container.start()
        else:
            logger.info(f" Creating Qdrant container '{config.QDRANT_DOCKER_CONTAINER_NAME}'...")
            client.containers.run(
                image,
                name=config.QDRANT_DOCKER_CONTAINER_NAME,
                detach=True,
                restart_policy={"Name": "unless-stopped"},
                ports={"6333/tcp": port, "6334/tcp": 6334},
                volumes={f"{config.QDRANT_DOCKER_CONTAINER_NAME}_data": {"bind": "/qdrant/storage", "mode": "rw"}},
            )
            container_name = config.QDRANT_DOCKER_CONTAINER_NAME

        logger.info(" Waiting for Qdrant to accept connections...")
        for _ in range(30):
            time_mod.sleep(1)
            try:
                qclient = QdrantClient(host=host, port=port, timeout=5.0)
                qclient.get_collections()
                logger.success(f" Qdrant Docker container ready on {host}:{port}")
                return qclient
            except Exception:
                logger.exception("Qdrant not accepting connections yet, retrying...")
        logger.error(" Qdrant container started but not accepting connections after 30s")
    except docker.errors.NotFound as e:  # type: ignore[attr-defined]
        logger.warning(" Docker container not found: %s", e)
    except docker.errors.APIError as e:  # type: ignore[attr-defined]
        logger.error(f" Docker API error: {e}")
    except FileNotFoundError:
        logger.warning(" Docker not found — cannot auto-start Qdrant")
    except Exception as e:
        logger.error(f" Docker auto-start failed: {e}")

    return None
