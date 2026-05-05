"""
좀비 프로세스 누적 시뮬레이션.

컨테이너 내부에서 자식 프로세스를 fork 한 뒤 부모가 wait() 하지 않아
좀비 상태(Z)를 의도적으로 생성하고 카운트를 상태 파일에 기록.

CLI:
  python simulate_zombie.py --container upstream_app --duration 30 --count 8
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


# ---------------------------------------------------------------------------
# 상태 파일 헬퍼
# ---------------------------------------------------------------------------

def _write_metric(key: str, value) -> None:
    path = Path(SCENARIO_STATUS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(path.read_text()) if path.exists() else {}
    except (json.JSONDecodeError, OSError):
        data = {}
    data[key] = value
    data["updated_at"] = int(time.time())
    path.write_text(json.dumps(data))


# ---------------------------------------------------------------------------
# 좀비 카운트 폴링
# ---------------------------------------------------------------------------

def _count_zombies(container: str) -> int:
    """컨테이너 내 좀비(Z) 상태 프로세스 수를 반환 (/proc 사용, ps 없어도 동작)."""
    cmd = [
        "docker", "exec", container, "sh", "-c",
        "grep -l 'Z (zombie)' /proc/*/status 2>/dev/null | wc -l",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return int(r.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        pass
    return 0


# ---------------------------------------------------------------------------
# 공개 시뮬레이션 함수
# ---------------------------------------------------------------------------

def simulate_zombie(
    container: str = "upstream_app",
    duration: int = 30,
    count: int = 8,
) -> tuple[bool, str]:
    print(f"[1] 좀비 프로세스 시뮬레이션 시작: container={container}, count={count}, duration={duration}s")

    # 컨테이너 내에서 실행할 Python 코드
    code = (
        f"import os, time, sys\n"
        f"n = {count}\n"
        f"for i in range(n):\n"
        f"    pid = os.fork()\n"
        f"    if pid == 0:\n"
        f"        os._exit(0)\n"
        f"print(f'Created {{n}} zombie children', flush=True)\n"
        f"time.sleep({duration})\n"
    )

    print(f"[2] 컨테이너 내부에서 좀비 생성 프로세스 시작")
    try:
        proc = subprocess.Popen(
            ["docker", "exec", container, "python3", "-c", code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        return False, "docker CLI 를 찾을 수 없습니다"

    # 잠시 대기 후 좀비 생성 확인
    time.sleep(2)

    print(f"[3] {duration}초 동안 좀비 카운트 폴링 (2초 간격)")
    elapsed = 0
    max_zombies = 0
    while elapsed < duration:
        zombie_count = _count_zombies(container)
        if zombie_count > max_zombies:
            max_zombies = zombie_count
        print(f"    elapsed={elapsed:3d}s | zombie_count={zombie_count}")
        _write_metric("zombie_process_count", zombie_count)
        time.sleep(2)
        elapsed += 2

        # 백그라운드 프로세스가 일찍 종료된 경우
        if proc.poll() is not None:
            break

    print(f"[4] 시뮬레이션 종료 - 최대 좀비 수: {max_zombies}")

    # 백그라운드 프로세스 종료
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    _write_metric("zombie_process_count", 0)
    return True, f"좀비 프로세스 시뮬레이션 완료: 최대 {max_zombies}개 좀비 감지"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="좀비 프로세스 누적 시뮬레이션")
    p.add_argument("--container", default="upstream_app", help="대상 컨테이너 이름")
    p.add_argument("--duration",  type=int, default=30,   help="시뮬레이션 지속 시간(초)")
    p.add_argument("--count",     type=int, default=8,    help="생성할 좀비 자식 프로세스 수")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    ok, msg = simulate_zombie(args.container, args.duration, args.count)
    print(msg)
    sys.exit(0 if ok else 1)
