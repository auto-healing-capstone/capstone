"""
데모 실행 전 인프라 상태 점검 및 시나리오 상태 파일 초기화.

기본값은 안전한 dry-run이며, 실제 초기화는 --apply 를 붙여 실행한다.

CLI:
  python infra/scripts/prepare_demo.py
  python infra/scripts/prepare_demo.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import time
from pathlib import Path


PROJECT_CONTAINERS = (
    "aiops_postgres",
    "target_nginx",
    "upstream_app",
    "aiops_agent",
    "aiops_prometheus",
    "aiops_alertmanager",
    "aiops_backend",
)

REQUIRED_PORTS = {
    5432: "PostgreSQL",
    8080: "target_nginx",
    8081: "upstream_app",
    9100: "agent",
    9090: "prometheus",
    9093: "alertmanager",
    8000: "backend",
}

SCENARIO_METRICS = {
    "nginx_5xx_total": 0,
    "db_active_connections": 0,
    "db_max_connections": 0,
    "container_oom_killed": 0,
    "db_deadlock_count": 0,
    "zombie_process_count": 0,
    "fd_usage_ratio": 0,
    "memory_leak_mb": 0,
}

LOAD_TEST_METRICS = {
    "memory_mb": 0,
    "disk_mb": 0,
}


def _docker(*args: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["docker", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        output = (result.stdout or "") + (result.stderr or "")
        return result.returncode == 0, output.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _write_status(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = dict(payload)
    data["updated_at"] = int(time.time())
    path.write_text(json.dumps(data), encoding="utf-8")


def reset_status_files() -> None:
    scenario_path = Path(
        os.getenv("SCENARIO_STATUS_FILE", "/tmp/auto-healing-scenarios/status.json")
    )
    load_test_path = Path(
        os.getenv("LOAD_TEST_STATUS_FILE", "/tmp/auto-healing-load-test/status.json")
    )
    _write_status(scenario_path, SCENARIO_METRICS)
    _write_status(load_test_path, LOAD_TEST_METRICS)
    print(f"[ok] reset {scenario_path}")
    print(f"[ok] reset {load_test_path}")


def print_port_report() -> None:
    print("[ports]")
    for port, owner in REQUIRED_PORTS.items():
        state = "open" if _port_open(port) else "free"
        print(f"  {port:<5} {owner:<16} {state}")


def print_container_report() -> None:
    print("[containers]")
    ok, output = _docker(
        "ps",
        "-a",
        "--format",
        "{{.Names}}\t{{.Status}}",
    )
    if not ok:
        print(f"  docker unavailable: {output}")
        return

    rows = {}
    for line in output.splitlines():
        if "\t" not in line:
            continue
        name, status = line.split("\t", 1)
        rows[name] = status

    for name in PROJECT_CONTAINERS:
        print(f"  {name:<20} {rows.get(name, 'missing')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="데모 인프라 사전 점검/초기화")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="status.json 파일을 실제로 초기화",
    )
    args = parser.parse_args()

    print_port_report()
    print_container_report()

    if args.apply:
        reset_status_files()
    else:
        print("[dry-run] status files were not changed. Use --apply to reset them.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
