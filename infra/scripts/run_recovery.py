"""
복구 스크립트 통합 실행기.

healing_service.py 에서 action_type + params dict 로 호출하거나
CLI 에서 직접 실행 가능.

지원 액션:
  update_resources      --container <name> [--memory 512m] [--cpus 1.5]
  reload_nginx          --container <name> [--config /path/to/conf]
  restart_container     --container <name>
  update_db_config      --container <name> --param <param> --value <val>
  cleanup_logs          --container <name> [--path /var/log]
  cleanup_disk          --container <name> [--path /tmp]
  simulate_nginx_5xx    [--duration 30] [--nginx-url http://localhost:8080]
  simulate_conn_pool    [--connections 20] [--duration 30]
  simulate_oom          --container <name> [--limit 64m]
  simulate_deadlock     [--rounds 3] [--container aiops_postgres]
  simulate_zombie       [--container upstream_app] [--duration 30] [--count 8]
  simulate_fd_exhaustion [--container upstream_app] [--duration 30]
  simulate_memory_leak  [--container upstream_app] [--target-mb 200] [--hold 30]

CLI 예시:
  python run_recovery.py update_resources --container aiops_postgres --memory 1g
  python run_recovery.py reload_nginx --container target_nginx
  python run_recovery.py cleanup_disk --container target_nginx --path /tmp

API 예시 (healing_service.py 에서):
  from infra.scripts.run_recovery import run_recovery
  ok, msg = run_recovery("restart_container", {"container": "target_nginx"})
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# 동일 패키지 내 스크립트 import
sys.path.insert(0, str(Path(__file__).parent))
from update_resources import update_resources
from reload_nginx import reload_nginx
from update_db_config import update_db_config
from simulate_nginx_5xx import simulate_nginx_5xx
from simulate_connection_pool import simulate_connection_pool
from simulate_oom import simulate_oom
from simulate_deadlock import simulate_deadlock
from simulate_zombie import simulate_zombie
from simulate_fd_exhaustion import simulate_fd_exhaustion
from simulate_memory_leak import simulate_memory_leak


# ── 개별 액션 함수 ──────────────────────────────────────────────────────────

def restart_container(container: str) -> tuple[bool, str]:
    try:
        r = subprocess.run(
            ["docker", "restart", container],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode == 0:
            return True, f"컨테이너 재시작 완료: {container}"
        return False, r.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, f"재시작 타임아웃 (60s): {container}"
    except FileNotFoundError:
        return False, "docker CLI를 찾을 수 없습니다"


def cleanup_logs(container: str, path: str = "/var/log") -> tuple[bool, str]:
    cmd = [
        "docker", "exec", container, "sh", "-c",
        f"find {path} -name '*.log' -mtime +1 -delete 2>&1 && echo 'cleanup done'",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return True, f"로그 정리 완료: {container}:{path}\n{r.stdout.strip()}"
        return False, r.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "로그 정리 타임아웃 (30s)"
    except FileNotFoundError:
        return False, "docker CLI를 찾을 수 없습니다"


def cleanup_disk(container: str, path: str = "/tmp") -> tuple[bool, str]:
    cmd = [
        "docker", "exec", container, "sh", "-c",
        f"find {path} -type f -mtime +0 -delete 2>&1 && echo 'cleanup done'",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return True, f"디스크 정리 완료: {container}:{path}"
        return False, r.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "디스크 정리 타임아웃 (30s)"
    except FileNotFoundError:
        return False, "docker CLI를 찾을 수 없습니다"


# ── 액션 라우팅 테이블 ──────────────────────────────────────────────────────

_ACTIONS: dict[str, object] = {
    "update_resources":  lambda p: update_resources(
        p["container"], p.get("memory"), p.get("memory_swap"), p.get("cpus")
    ),
    "reload_nginx":      lambda p: reload_nginx(
        p.get("container", "target_nginx"), p.get("config")
    ),
    "restart_container": lambda p: restart_container(p["container"]),
    "update_db_config":  lambda p: update_db_config(
        p["container"], p["param"], p["value"],
        p.get("db_user", "postgres"), p.get("db_name", "postgres"),
    ),
    "cleanup_logs":      lambda p: cleanup_logs(
        p["container"], p.get("path", "/var/log")
    ),
    "cleanup_disk":      lambda p: cleanup_disk(
        p["container"], p.get("path", "/tmp")
    ),
    "simulate_nginx_5xx": lambda p: simulate_nginx_5xx(
        p.get("duration", 30), p.get("nginx_url", "http://localhost:8080"),
        p.get("restore", True),
    ),
    "simulate_conn_pool": lambda p: simulate_connection_pool(
        p.get("connections", 20), p.get("duration", 30),
        p.get("host", "localhost"), p.get("port", 5432),
        p.get("user", "postgres"), p.get("password", ""), p.get("db", "postgres"),
    ),
    "simulate_oom":      lambda p: simulate_oom(
        p.get("container", "target_nginx"), p.get("limit", "64m"),
        p.get("restore", True),
    ),
    "simulate_deadlock":     lambda p: simulate_deadlock(
        p.get("rounds", 3),
        p.get("container", "aiops_postgres"),
        p.get("user", "aiops_user"),
        p.get("db", "aiops_db"),
    ),
    "simulate_zombie":       lambda p: simulate_zombie(
        p.get("container", "upstream_app"), p.get("duration", 30), p.get("count", 8),
    ),
    "simulate_fd_exhaustion": lambda p: simulate_fd_exhaustion(
        p.get("container", "upstream_app"), p.get("duration", 30),
    ),
    "simulate_memory_leak":  lambda p: simulate_memory_leak(
        p.get("container", "upstream_app"), p.get("target_mb", 200), p.get("hold", 30),
    ),
}


# ── 공개 API ───────────────────────────────────────────────────────────────

def run_recovery(action_type: str, params: dict) -> tuple[bool, str]:
    """
    healing_service.py 에서 직접 임포트하여 호출하는 진입점.

    Args:
        action_type: 지원 액션 이름 (위 _ACTIONS 키)
        params:      액션별 필요 파라미터 dict

    Returns:
        (is_successful: bool, log_message: str)
    """
    handler = _ACTIONS.get(action_type)
    if handler is None:
        supported = ", ".join(_ACTIONS)
        return False, f"알 수 없는 액션: '{action_type}'. 지원 액션: {supported}"
    try:
        return handler(params)
    except KeyError as e:
        return False, f"필수 파라미터 누락: {e}"
    except Exception as e:
        return False, f"복구 실행 중 예외: {type(e).__name__}: {e}"


# ── CLI 인터페이스 ──────────────────────────────────────────────────────────

def _build_cli() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="복구 스크립트 통합 실행기",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="action", required=True)

    r = sub.add_parser("update_resources", help="컨테이너 CPU/메모리 제한 변경")
    r.add_argument("--container", required=True)
    r.add_argument("--memory", help="메모리 상한 (예: 512m, 1g)")
    r.add_argument("--memory-swap", dest="memory_swap")
    r.add_argument("--cpus", help="CPU 코어 수 (예: 1.5)")

    n = sub.add_parser("reload_nginx", help="Nginx 무중단 설정 리로드")
    n.add_argument("--container", default="target_nginx")
    n.add_argument("--config", dest="config", help="새 nginx.conf 경로")

    rc = sub.add_parser("restart_container", help="컨테이너 재시작")
    rc.add_argument("--container", required=True)

    d = sub.add_parser("update_db_config", help="PostgreSQL 파라미터 변경")
    d.add_argument("--container", default="aiops_postgres")
    d.add_argument("--param", required=True)
    d.add_argument("--value", required=True)
    d.add_argument("--db-user", dest="db_user", default="postgres")

    cl = sub.add_parser("cleanup_logs", help="오래된 로그 파일 정리")
    cl.add_argument("--container", required=True)
    cl.add_argument("--path", default="/var/log")

    cd = sub.add_parser("cleanup_disk", help="임시 파일 정리")
    cd.add_argument("--container", required=True)
    cd.add_argument("--path", default="/tmp")

    nx = sub.add_parser("simulate_nginx_5xx", help="Nginx 5xx 에러 시뮬레이션")
    nx.add_argument("--duration", type=int, default=30, help="시뮬레이션 지속 시간(초)")
    nx.add_argument("--nginx-url", dest="nginx_url", default="http://localhost:8080")
    nx.add_argument("--no-restore", dest="restore", action="store_false", default=True)

    cp = sub.add_parser("simulate_conn_pool", help="PostgreSQL 커넥션 풀 고갈 시뮬레이션")
    cp.add_argument("--connections", type=int, default=20, help="동시 연결 시도 수")
    cp.add_argument("--duration", type=int, default=30, help="연결 유지 시간(초)")
    cp.add_argument("--host", default="localhost")
    cp.add_argument("--port", type=int, default=5432)
    cp.add_argument("--user", default="postgres")
    cp.add_argument("--password", default="")
    cp.add_argument("--db", default="postgres")

    oom = sub.add_parser("simulate_oom", help="OOM Killer 시뮬레이션")
    oom.add_argument("--container", default="target_nginx")
    oom.add_argument("--limit", default="64m", help="설정할 메모리 제한")
    oom.add_argument("--no-restore", dest="restore", action="store_false", default=True)

    dl = sub.add_parser("simulate_deadlock", help="PostgreSQL DB 데드락 시뮬레이션")
    dl.add_argument("--rounds", type=int, default=3, help="데드락 반복 횟수")
    dl.add_argument("--container", default="aiops_postgres")
    dl.add_argument("--user", default="aiops_user")
    dl.add_argument("--db", default="aiops_db")

    zb = sub.add_parser("simulate_zombie", help="좀비 프로세스 누적 시뮬레이션")
    zb.add_argument("--container", default="upstream_app")
    zb.add_argument("--duration", type=int, default=30, help="시뮬레이션 지속 시간(초)")
    zb.add_argument("--count", type=int, default=8, help="생성할 좀비 자식 프로세스 수")

    fd = sub.add_parser("simulate_fd_exhaustion", help="파일 디스크립터 고갈 시뮬레이션")
    fd.add_argument("--container", default="upstream_app")
    fd.add_argument("--duration", type=int, default=30, help="시뮬레이션 지속 시간(초)")

    ml = sub.add_parser("simulate_memory_leak", help="점진적 메모리 누수 시뮬레이션")
    ml.add_argument("--container", default="upstream_app")
    ml.add_argument("--target-mb", dest="target_mb", type=int, default=200)
    ml.add_argument("--hold", type=int, default=30, help="목표 도달 후 유지 시간(초)")

    return p


if __name__ == "__main__":
    parser = _build_cli()
    args = vars(parser.parse_args())
    action = args.pop("action")
    ok, msg = run_recovery(action, args)
    print(msg)
    sys.exit(0 if ok else 1)
