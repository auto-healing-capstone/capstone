"""
컨테이너 CPU/메모리 리소스 제한을 런타임에 변경 (docker update).

CLI:
  python update_resources.py --container target_nginx --memory 512m --cpus 1.5
  python update_resources.py --container aiops_postgres --memory 1g

API:
  from update_resources import update_resources
  ok, msg = update_resources("target_nginx", memory="512m", cpus="1.5")
"""
from __future__ import annotations

import argparse
import subprocess
import sys


def update_resources(
    container: str,
    memory: str | None = None,
    memory_swap: str | None = None,
    cpus: str | None = None,
) -> tuple[bool, str]:
    """
    docker update 로 런타임 리소스 제한 변경.

    Args:
        container:    컨테이너 이름 또는 ID
        memory:       메모리 상한 (예: "512m", "1g")
        memory_swap:  스왑 포함 상한 ("-1" 이면 무제한). 미지정 시 memory 와 동일 설정
        cpus:         CPU 코어 수 상한 (예: "1.5")

    Returns:
        (True, 결과 메시지) 또는 (False, 에러 메시지)
    """
    if not any([memory, memory_swap, cpus]):
        return False, "변경할 파라미터를 하나 이상 지정하세요 (--memory / --cpus)"

    cmd = ["docker", "update"]
    if memory:
        cmd += ["--memory", memory]
        # swap 미지정 시 memory 와 동일하게 설정 → 추가 스왑 없음
        cmd += ["--memory-swap", memory_swap if memory_swap else memory]
    elif memory_swap:
        cmd += ["--memory-swap", memory_swap]
    if cpus:
        cmd += ["--cpus", cpus]
    cmd.append(container)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return False, "docker update 타임아웃 (30s)"
    except FileNotFoundError:
        return False, "docker CLI를 찾을 수 없습니다"

    if result.returncode != 0:
        return False, result.stderr.strip() or result.stdout.strip()

    parts = [f"container={container}"]
    if memory:
        parts.append(f"memory={memory}")
    if cpus:
        parts.append(f"cpus={cpus}")
    return True, "리소스 제한 업데이트 완료: " + ", ".join(parts)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="런타임 컨테이너 리소스 제한 변경 (docker update)")
    p.add_argument("--container", required=True, help="컨테이너 이름 또는 ID")
    p.add_argument("--memory", help="메모리 상한 (예: 512m, 1g)")
    p.add_argument("--memory-swap", dest="memory_swap", help="스왑 포함 상한 (-1: 무제한)")
    p.add_argument("--cpus", help="CPU 코어 수 상한 (예: 1.5)")
    return p.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    ok, msg = update_resources(args.container, args.memory, args.memory_swap, args.cpus)
    print(msg)
    sys.exit(0 if ok else 1)
