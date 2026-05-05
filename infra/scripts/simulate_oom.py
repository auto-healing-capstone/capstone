"""
OOM Killer 시뮬레이션.

컨테이너에 낮은 메모리 제한을 설정하고 내부에서 메모리를 초과 할당해
OOM Killer를 유발. OOMKilled 상태를 시나리오 상태 파일에 기록.

CLI:
  python simulate_oom.py --container target_nginx --limit 64m
  python simulate_oom.py --container upstream_app --limit 32m --no-restore
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SCENARIO_STATUS_FILE = os.getenv(
    "SCENARIO_STATUS_FILE", "/tmp/auto-healing-scenarios/status.json"
)


def _docker(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker"] + list(args), capture_output=True, text=True, timeout=timeout
    )


def _write_metric(oom_count: int) -> None:
    path = Path(SCENARIO_STATUS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(path.read_text()) if path.exists() else {}
    except (json.JSONDecodeError, OSError):
        data = {}
    data["container_oom_killed"] = oom_count
    data["updated_at"] = int(time.time())
    path.write_text(json.dumps(data))


def is_oom_killed(container: str) -> bool:
    r = _docker("inspect", "--format", "{{.State.OOMKilled}}", container)
    return r.returncode == 0 and r.stdout.strip().lower() == "true"


def simulate_oom(
    container: str = "target_nginx",
    limit: str = "64m",
    restore: bool = True,
) -> tuple[bool, str]:
    # 현재 메모리 제한 저장
    r = _docker("inspect", "--format", "{{.HostConfig.Memory}}", container)
    original_limit = r.stdout.strip() if r.returncode == 0 else "0"
    print(f"[1] 현재 메모리 제한: {original_limit} bytes (0 = 무제한)")

    # 낮은 메모리 제한 설정
    print(f"[2] 메모리 제한 설정 → {limit}")
    r = _docker("update", f"--memory={limit}", f"--memory-swap={limit}", container)
    if r.returncode != 0:
        return False, f"메모리 제한 설정 실패: {r.stderr.strip()}"

    # 컨테이너 재시작 (새 제한 적용)
    print(f"[3] 컨테이너 재시작")
    r = _docker("restart", container)
    if r.returncode != 0:
        return False, f"컨테이너 재시작 실패: {r.stderr.strip()}"
    time.sleep(2)

    # 메모리 초과 할당 (여러 명령어 순서대로 시도)
    print(f"[4] 메모리 초과 할당 실행 → OOM Killer 유발")
    alloc_cmd = (
        # 방법 1: dd로 /dev/shm에 대용량 쓰기
        "dd if=/dev/zero of=/dev/shm/oom_test bs=1M count=256 2>/dev/null; "
        # 방법 2: /tmp에 대용량 파일 생성
        "dd if=/dev/zero of=/tmp/oom_test bs=1M count=256 2>/dev/null; "
        # 방법 3: yes 명령어로 메모리 압박
        "yes | head -c 268435456 > /dev/null 2>&1"
    )
    _docker("exec", container, "sh", "-c", alloc_cmd, timeout=15)

    # OOMKilled 여부 확인
    time.sleep(1)
    oom_killed = is_oom_killed(container)
    print(f"[5] OOMKilled 상태: {oom_killed}")
    _write_metric(1 if oom_killed else 0)

    # 메모리 제한 복원
    if restore:
        print(f"[6] 메모리 제한 복원 (무제한)")
        _docker("update", "--memory=0", "--memory-swap=0", container)
        _docker("restart", container)
        time.sleep(2)
        _write_metric(0)

    if oom_killed:
        return True, f"OOM Killer 발동 확인: {container} (limit={limit})"
    return True, f"OOM 시뮬레이션 실행 완료 (OOMKilled={oom_killed}, limit={limit})"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="OOM Killer 시뮬레이션")
    p.add_argument("--container", default="target_nginx", help="대상 컨테이너")
    p.add_argument("--limit", default="64m", help="설정할 메모리 제한 (예: 64m, 128m)")
    p.add_argument("--no-restore", dest="restore", action="store_false", default=True,
                   help="시뮬레이션 후 메모리 제한 복원 생략")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    ok, msg = simulate_oom(args.container, args.limit, args.restore)
    print(msg)
    sys.exit(0 if ok else 1)
