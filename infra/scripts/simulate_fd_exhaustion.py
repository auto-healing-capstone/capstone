"""
파일 디스크립터(FD) 고갈 시뮬레이션.

컨테이너 내부에서 FD soft limit 의 95% 를 /dev/null 열기로 소진하고
폴링을 통해 FD 사용률을 상태 파일에 기록.

CLI:
  python simulate_fd_exhaustion.py --container upstream_app --duration 30
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

# unlimited 환경에서 실용적인 상한 (실제로 이만큼만 열어도 충분히 시뮬레이션 가능)
_MAX_PRACTICAL_LIMIT = 8192


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
# FD soft limit 조회
# ---------------------------------------------------------------------------

def _get_fd_soft_limit(container: str) -> int:
    """컨테이너의 FD soft limit (ulimit -n) 을 반환. unlimited → _MAX_PRACTICAL_LIMIT."""
    cmd = ["docker", "exec", container, "sh", "-c", "ulimit -n"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            val = r.stdout.strip()
            if val.lower() == "unlimited":
                return _MAX_PRACTICAL_LIMIT
            n = int(val)
            return min(n, _MAX_PRACTICAL_LIMIT)
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        pass
    return 1024


# ---------------------------------------------------------------------------
# 현재 FD 사용량 폴링
# ---------------------------------------------------------------------------

def _get_fd_count(container: str, marker: str) -> int:
    """마커 문자열로 식별한 python3 프로세스의 FD 수를 반환."""
    # marker 를 포함한 python3 프로세스의 PID 를 /proc 에서 찾는다
    cmd = [
        "docker", "exec", container, "sh", "-c",
        f"for p in /proc/[0-9]*/cmdline; do "
        f"  grep -q '{marker}' \"$p\" 2>/dev/null && "
        f"  echo $(ls $(dirname $p)/fd 2>/dev/null | wc -l) && break; "
        f"done",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return int(r.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        pass
    return 0


# ---------------------------------------------------------------------------
# 공개 시뮬레이션 함수
# ---------------------------------------------------------------------------

def simulate_fd_exhaustion(
    container: str = "upstream_app",
    duration: int = 30,
) -> tuple[bool, str]:
    print(f"[1] FD 고갈 시뮬레이션 시작: container={container}, duration={duration}s")

    soft_limit = _get_fd_soft_limit(container)
    target_fds = int(soft_limit * 0.95)
    print(f"[2] FD soft limit={soft_limit}, target={target_fds}")

    # 컨테이너 내에서 실행할 Python 코드
    # MARKER 를 코드에 삽입해 프로세스 식별에 사용
    marker = "FD_EXHAUST_SIM"
    code = (
        f"# {marker}\n"
        f"import resource, os, time, sys\n"
        f"target = {target_fds}\n"
        f"fds = []\n"
        f"for i in range(target):\n"
        f"    try:\n"
        f"        fds.append(open('/dev/null', 'r'))\n"
        f"    except OSError:\n"
        f"        break\n"
        f"print(f'Opened {{len(fds)}} FDs', flush=True)\n"
        f"time.sleep({duration})\n"
        f"for f in fds:\n"
        f"    try: f.close()\n"
        f"    except: pass\n"
    )

    print(f"[3] 컨테이너 내부에서 FD 소진 프로세스 시작")
    try:
        proc = subprocess.Popen(
            ["docker", "exec", container, "python3", "-c", code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        return False, "docker CLI 를 찾을 수 없습니다"

    # FD 가 실제로 열리기까지 대기
    time.sleep(4)

    print(f"[4] {duration}초 동안 FD 사용률 폴링 (3초 간격)")
    elapsed = 4
    max_ratio = 0.0
    while elapsed < duration:
        fd_count = _get_fd_count(container, marker)
        ratio = fd_count / soft_limit if soft_limit > 0 else 0.0
        ratio = min(ratio, 1.0)
        if ratio > max_ratio:
            max_ratio = ratio
        print(f"    elapsed={elapsed:3d}s | fd_count={fd_count}, limit={soft_limit}, ratio={ratio:.3f}")
        _write_metric("fd_usage_ratio", round(ratio, 4))
        time.sleep(3)
        elapsed += 3

        if proc.poll() is not None:
            break

    print(f"[5] 시뮬레이션 종료 - 최대 FD 사용률: {max_ratio:.3f}")

    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    _write_metric("fd_usage_ratio", 0.0)
    return True, f"FD 고갈 시뮬레이션 완료: 최대 사용률 {max_ratio:.1%} (limit={soft_limit}, target={target_fds})"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="파일 디스크립터 고갈 시뮬레이션")
    p.add_argument("--container", default="upstream_app", help="대상 컨테이너 이름")
    p.add_argument("--duration",  type=int, default=30,   help="시뮬레이션 지속 시간(초)")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    ok, msg = simulate_fd_exhaustion(args.container, args.duration)
    print(msg)
    sys.exit(0 if ok else 1)
