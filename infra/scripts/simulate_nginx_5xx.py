"""
Nginx 5xx 에러 시뮬레이션.

upstream_app 컨테이너를 중단해 nginx가 502 Bad Gateway를 반환하게 유도.
시뮬레이션 중 5xx 카운트를 시나리오 상태 파일에 기록해 Prometheus가 감지하게 함.

CLI:
  python simulate_nginx_5xx.py --duration 30
  python simulate_nginx_5xx.py --duration 60 --nginx-url http://localhost:8080
  python simulate_nginx_5xx.py --no-restore   # upstream을 재시작하지 않음
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

UPSTREAM_CONTAINER = "upstream_app"
NGINX_URL = "http://localhost:8080"
SCENARIO_STATUS_FILE = os.getenv(
    "SCENARIO_STATUS_FILE", "/tmp/auto-healing-scenarios/status.json"
)


def _docker(*args: str) -> tuple[bool, str]:
    r = subprocess.run(
        ["docker"] + list(args), capture_output=True, text=True, timeout=30
    )
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def _http_status(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def _write_metric(key: str, value: float) -> None:
    path = Path(SCENARIO_STATUS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(path.read_text()) if path.exists() else {}
    except (json.JSONDecodeError, OSError):
        data = {}
    data[key] = value
    data["updated_at"] = int(time.time())
    path.write_text(json.dumps(data))


def simulate_nginx_5xx(
    duration: int = 30,
    nginx_url: str = NGINX_URL,
    restore: bool = True,
) -> tuple[bool, str]:
    print(f"[1] upstream_app 컨테이너 중단 → nginx 502 유발")
    ok, msg = _docker("stop", UPSTREAM_CONTAINER)
    if not ok:
        return False, f"upstream_app 중단 실패: {msg}"

    print(f"[2] {duration}초 동안 nginx 응답 모니터링...")
    five_xx_count = 0
    for i in range(duration):
        code = _http_status(nginx_url)
        if code in (502, 503, 504):
            five_xx_count += 1
        _write_metric("nginx_5xx_total", five_xx_count)
        print(f"  [{i+1:3d}s] HTTP {code}  (5xx 누적: {five_xx_count})")
        time.sleep(1)

    result_msg = f"Nginx 5xx 시뮬레이션 완료 - 5xx 감지 {five_xx_count}건"

    if restore:
        print(f"[3] upstream_app 재시작 → 복구")
        _docker("start", UPSTREAM_CONTAINER)
        time.sleep(2)
        _write_metric("nginx_5xx_total", 0)

    return five_xx_count > 0, result_msg


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Nginx 5xx 에러 시뮬레이션")
    p.add_argument("--duration", type=int, default=30, help="시뮬레이션 지속 시간(초)")
    p.add_argument("--nginx-url", default=NGINX_URL, help="Nginx 엔드포인트 URL")
    p.add_argument("--no-restore", dest="restore", action="store_false", default=True,
                   help="시뮬레이션 후 upstream 재시작 생략")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    ok, msg = simulate_nginx_5xx(args.duration, args.nginx_url, args.restore)
    print(msg)
    sys.exit(0 if ok else 1)
