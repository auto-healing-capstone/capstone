# backend/app/integrations/docker_client.py
import logging
from typing import Optional

import docker
import docker.errors
from docker import DockerClient

logger = logging.getLogger(__name__)

_client: DockerClient | None = None
_connect_failed: bool = False


def get_docker_client() -> DockerClient | None:
    global _client, _connect_failed
    if _connect_failed:
        return None
    if _client is None:
        try:
            _client = docker.from_env()
        except Exception:
            _connect_failed = True
            logger.error("Failed to connect to Docker daemon", exc_info=True)
    return _client


def restart_container(container_name: str) -> bool:
    client = get_docker_client()
    if client is None:
        return False
    try:
        container = client.containers.get(container_name)
        container.restart()
        return True
    except docker.errors.NotFound:
        logger.error("Container not found: %s", container_name)
    except docker.errors.APIError:
        logger.error(
            "Docker API error restarting container: %s", container_name, exc_info=True
        )
    return False


def update_container(
    container_name: str,
    mem_limit: Optional[str] = None,
    cpu_quota: Optional[int] = None,
) -> bool:
    client = get_docker_client()
    if client is None:
        return False
    try:
        container = client.containers.get(container_name)
        kwargs: dict = {}
        if mem_limit is not None:
            kwargs["mem_limit"] = mem_limit
        if cpu_quota is not None:
            kwargs["cpu_quota"] = cpu_quota
        container.update(**kwargs)
        return True
    except docker.errors.NotFound:
        logger.error("Container not found: %s", container_name)
    except docker.errors.APIError:
        logger.error(
            "Docker API error updating container: %s", container_name, exc_info=True
        )
    return False
