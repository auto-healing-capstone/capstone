"""
점진적 메모리 누수 시뮬레이션.

컨테이너 내부에서 10MB 단위로 메모리를 할당해 누수를 모방하고
docker stats 를 통해 실제 메모리 사용량을 폴링해 상태 파일에 기록.

CLI:
  python simulate_memory_leak.py --container upstream_app --target-mb 200 --hold 30
"""
from __future__ import annotations

import argparse
import json
import os
import re
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
# 메모리 사용량 파싱
# ---------------------------------------------------------------------------

_UNIT_MB = {
    "b":   1 / (1024 * 1024),
    "kib": 1 / 1024,
    "mib": 1.0,
    "gib": 1024.0,
    "kb":  1 / 1024,
    "mb":  1.0,
    "gb":  1024.0,
}


def _parse_mem_mb(mem_str: str) -> float:
    """
    docker stats --format "{{.MemUsage}}" 의 첫 번째 값을 MB 로 변환.
    예: "45.2MiB / 7.669GiB" -> 45.2
        "512KiB / 2GiB"      -> 0.5
    """
    part = mem_str.split("/")[0].strip()
    m = re.match(r"([\d.]+)\s*([a-zA-Z]+)", part)
    if not m:
        return 0.0
    number = float(m.group(1))
    unit   = m.group(2).lower()
    factor = _UNIT_MB.get(unit, 1.0)
    return round(number * factor, 2)


# ---------------------------------------------------------------------------
# 현재 컨테이너 메모리 사용량 조회
# ---------------------------------------------------------------------------

def _get_mem_mb(container: str) -> float:
    cmd = [
        "docker", "stats", "--no-stream",
        "--format", "{{.MemUsage}}",
        container,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and r.stdout.strip():
            return _parse_mem_mb(r.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return 0.0


# ---------------------------------------------------------------------------
# 공개 시뮬레이션 함수
# ---------------------------------------------------------------------------

def simulate_memory_leak(
    container: str = "upstream_app",
    target_mb: int = 200,
    hold: int = 30,
) -> tuple[bool, str]:
    print(f"[1] 메모리 누수 시뮬레이션 시작: container={container}, target={target_mb}MB, hold={hold}s")

    # 컨테이너 내에서 실행할 Python 코드
    # target_mb * 2 를 sleep 총합으로 사용해 할당 완료 후 hold 유지
    total_sleep = target_mb // 10 * 2 + hold  # 할당 시간 + hold 여유
    code = (
        f"import time, sys\n"
        f"target_mb = {target_mb}\n"
        f"step_mb = 10\n"
        f"leaked = []\n"
        f"total = 0\n"
        f"while total < target_mb:\n"
        f"    leaked.append(bytearray(step_mb * 1024 * 1024))\n"
        f"    total += step_mb\n"
        f"    print(f'Leaked {{total}}MB', flush=True)\n"
        f"    time.sleep(2)\n"
        f"print(f'Holding {{total}}MB...', flush=True)\n"
        f"time.sleep({hold})\n"
        f"leaked.clear()\n"
    )

    print(f"[2] 컨테이너 내부에서 메모리 누수 프로세스 시작")
    try:
        proc = subprocess.Popen(
            ["docker", "exec", container, "python3", "-c", code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        return False, "docker CLI 를 찾을 수 없습니다"

    # 잠시 후부터 폴링 - 할당+hold 기간 동안 진행
    total_duration = (target_mb // 10) * 2 + hold
    print(f"[3] {total_duration}초 동안 메모리 사용량 폴링 (3초 간격)")

    elapsed = 0
    max_mem_mb = 0.0
    while elapsed < total_duration:
        mem_mb = _get_mem_mb(container)
        if mem_mb > max_mem_mb:
            max_mem_mb = mem_mb
        print(f"    elapsed={elapsed:3d}s | mem_mb={mem_mb:.1f}")
        _write_metric("memory_leak_mb", round(mem_mb, 2))
        time.sleep(3)
        elapsed += 3

        if proc.poll() is not None:
            break

    print(f"[4] 시뮬레이션 종료 - 최대 메모리 사용량: {max_mem_mb:.1f}MB")

    # 백그라운드 프로세스 종료
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    _write_metric("memory_leak_mb", 0)
    return True, f"메모리 누수 시뮬레이션 완료: 최대 {max_mem_mb:.1f}MB 사용 (target={target_mb}MB)"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="점진적 메모리 누수 시뮬레이션")
    p.add_argument("--container",  default="upstream_app", help="대상 컨테이너 이름")
    p.add_argument("--target-mb",  dest="target_mb", type=int, default=200,
                   help="누수 목표 메모리 (MB)")
    p.add_argument("--hold",       type=int, default=30,
                   help="목표 도달 후 유지 시간(초)")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    ok, msg = simulate_memory_leak(args.container, args.target_mb, args.hold)
    print(msg)
    sys.exit(0 if ok else 1)
