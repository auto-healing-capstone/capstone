"""
Docker socket을 통한 컨테이너 상태 조회 유틸리티.
subprocess로 docker CLI를 호출하므로 docker Python SDK 불필요.
"""
from __future__ import annotations

import json
import subprocess


def _docker(*args: str, timeout: int = 10) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker"] + list(args), capture_output=True, text=True, timeout=timeout
    )


def get_container_stats(container_name: str) -> dict | None:
    """컨테이너 CPU/메모리 사용량 반환 (docker stats --no-stream)."""
    r = _docker(
        "stats", "--no-stream", "--format",
        '{"cpu":"{{.CPUPerc}}","mem":"{{.MemUsage}}","mem_perc":"{{.MemPerc}}"}',
        container_name,
    )
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout.strip())
    except (json.JSONDecodeError, ValueError):
        return None


def is_container_oom_killed(container_name: str) -> bool:
    """컨테이너가 OOM Kill 당했는지 여부 반환."""
    r = _docker("inspect", "--format", "{{.State.OOMKilled}}", container_name)
    return r.returncode == 0 and r.stdout.strip().lower() == "true"


def get_container_status(container_name: str) -> str | None:
    """컨테이너 실행 상태 반환 (running, exited, restarting, ...)."""
    r = _docker("inspect", "--format", "{{.State.Status}}", container_name)
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def list_oom_killed_containers() -> list[str]:
    """OOM Kill 당한 모든 컨테이너 이름 목록 반환."""
    r = _docker(
        "ps", "-a", "--format",
        '{"name":"{{.Names}}","status":"{{.Status}}"}',
    )
    if r.returncode != 0:
        return []

    oom_containers = []
    for line in r.stdout.strip().splitlines():
        try:
            info = json.loads(line)
            if is_container_oom_killed(info["name"]):
                oom_containers.append(info["name"])
        except (json.JSONDecodeError, KeyError):
            continue
    return oom_containers
