# backend/app/integrations/docker_client.py
import logging
import time
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
        start = time.perf_counter()
        container = client.containers.get(container_name)
        container.restart()
        logger.info(
            "[TIMING] restart_container completed in %.2fs", time.perf_counter() - start
        )
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
        start = time.perf_counter()
        container = client.containers.get(container_name)
        kwargs: dict = {}
        if mem_limit is not None:
            kwargs["mem_limit"] = mem_limit
        if cpu_quota is not None:
            kwargs["cpu_quota"] = cpu_quota
        if not kwargs:
            logger.error(
                "No update parameters provided for container: %s", container_name
            )
            return False
        container.update(**kwargs)
        logger.info(
            "[TIMING] update_container completed in %.2fs", time.perf_counter() - start
        )
        return True
    except docker.errors.NotFound:
        logger.error("Container not found: %s", container_name)
    except docker.errors.APIError:
        logger.error(
            "Docker API error updating container: %s", container_name, exc_info=True
        )
    return False


def clear_logs(container_name: str) -> bool:
    client = get_docker_client()
    if client is None:
        return False
    try:
        start = time.perf_counter()
        container = client.containers.get(container_name)
        exit_code, output = container.exec_run("find /var/log -name '*.log' -delete")
        if exit_code != 0:
            logger.error(
                "clear_logs failed for container %s (exit %d): %s",
                container_name,
                exit_code,
                output,
            )
            return False
        logger.info(
            "[TIMING] clear_logs completed in %.2fs", time.perf_counter() - start
        )
        return True
    except docker.errors.NotFound:
        logger.error("Container not found: %s", container_name)
    except docker.errors.APIError:
        logger.error(
            "Docker API error clearing logs for container: %s",
            container_name,
            exc_info=True,
        )
    return False


def docker_prune() -> bool:
    client = get_docker_client()
    if client is None:
        return False
    try:
        start = time.perf_counter()
        images_prune_result = client.images.prune()
        volumes_prune_result = client.volumes.prune()
        logger.info("Docker image prune completed: %s", images_prune_result)
        logger.info("Docker volume prune completed: %s", volumes_prune_result)
        logger.info(
            "[TIMING] docker_prune completed in %.2fs", time.perf_counter() - start
        )
        return True
    except docker.errors.APIError:
        logger.error("Docker API error during prune", exc_info=True)
    return False


def restart_process(container_name: str, process: str = "nginx") -> bool:
    client = get_docker_client()
    if client is None:
        return False
    allowed_processes = {"nginx", "gunicorn", "uvicorn"}
    if process not in allowed_processes:
        logger.error("Process not allowed: %s", process)
        return False
    try:
        start = time.perf_counter()
        container = client.containers.get(container_name)
        exit_code, output = container.exec_run(f"sh -c 'kill -HUP $(pidof {process})'")
        if exit_code != 0:
            logger.error(
                "restart_process failed for '%s' in container %s (exit %d): %s",
                process,
                container_name,
                exit_code,
                output,
            )
            return False
        logger.info(
            "[TIMING] restart_process completed in %.2fs", time.perf_counter() - start
        )
        return True
    except docker.errors.NotFound:
        logger.error("Container not found: %s", container_name)
    except docker.errors.APIError:
        logger.error(
            "Docker API error restarting process '%s' in container: %s",
            process,
            container_name,
            exc_info=True,
        )
    return False
