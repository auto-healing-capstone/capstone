"""
PostgreSQL 런타임 파라미터 변경 (ALTER SYSTEM).

- 즉시 반영 가능한 파라미터: ALTER SYSTEM → pg_reload_conf()
- 재시작 필요한 파라미터:   ALTER SYSTEM 으로 저장 후 재시작 안내
  (max_connections, shared_buffers 등은 docker-compose command 인자로 초기 설정 권장)

CLI:
  python update_db_config.py --container aiops_postgres --param work_mem --value 16MB
  python update_db_config.py --container aiops_postgres --param max_connections --value 200

API:
  from update_db_config import update_db_config
  ok, msg = update_db_config("aiops_postgres", "work_mem", "16MB")
"""
from __future__ import annotations

import argparse
import subprocess
import sys

# pg_reload_conf() 로 즉시 반영되는 파라미터
_RELOAD_PARAMS: frozenset[str] = frozenset({
    "work_mem",
    "maintenance_work_mem",
    "log_min_duration_statement",
    "log_level",
    "statement_timeout",
    "idle_in_transaction_session_timeout",
    "lock_timeout",
    "temp_file_limit",
})

# ALTER SYSTEM 가능하지만 컨테이너 재시작 필요한 파라미터
_RESTART_PARAMS: frozenset[str] = frozenset({
    "max_connections",
    "shared_buffers",
    "max_wal_size",
    "wal_buffers",
    "max_prepared_transactions",
})


def update_db_config(
    container: str,
    param: str,
    value: str,
    db_user: str = "postgres",
    db_name: str = "postgres",
) -> tuple[bool, str]:
    """
    ALTER SYSTEM 으로 PostgreSQL 파라미터 변경.

    Args:
        container: DB 컨테이너 이름
        param:     변경할 파라미터 이름
        value:     새 값
        db_user:   psql 접속 사용자

    Returns:
        (True, 결과 메시지) 또는 (False, 에러 메시지)
    """
    def _psql(sql: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["docker", "exec", container, "psql", "-U", db_user, "-d", db_name, "-c", sql],
            capture_output=True, text=True, timeout=15,
        )

    # ALTER SYSTEM 실행
    alter = _psql(f"ALTER SYSTEM SET {param} = '{value}';")
    if alter.returncode != 0:
        return False, f"ALTER SYSTEM 실패: {alter.stderr.strip()}"

    # 즉시 반영 가능한 파라미터 → pg_reload_conf()
    if param in _RELOAD_PARAMS:
        reload = _psql("SELECT pg_reload_conf();")
        if reload.returncode != 0:
            return False, f"pg_reload_conf() 실패: {reload.stderr.strip()}"
        return True, f"SET {param}='{value}' 즉시 반영 완료"

    # 재시작 필요한 파라미터
    if param in _RESTART_PARAMS:
        return True, (
            f"SET {param}='{value}' postgresql.auto.conf 저장 완료. "
            f"적용하려면 컨테이너를 재시작하세요:\n"
            f"  docker restart {container}"
        )

    # 알 수 없는 파라미터 → reload 시도
    reload = _psql("SELECT pg_reload_conf();")
    if reload.returncode == 0:
        return True, f"SET {param}='{value}' 저장 및 reload 완료 (즉시 반영 여부 미보장)"
    return True, f"SET {param}='{value}' 저장 완료 (재시작 필요할 수 있음)"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PostgreSQL 런타임 파라미터 변경")
    p.add_argument("--container", default="aiops_postgres", help="DB 컨테이너 이름")
    p.add_argument("--param", required=True, help="파라미터 이름 (예: max_connections)")
    p.add_argument("--value", required=True, help="새 값 (예: 200, 16MB)")
    p.add_argument("--db-user", default="postgres", dest="db_user")
    p.add_argument("--db-name", default="postgres", dest="db_name")
    return p.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    ok, msg = update_db_config(args.container, args.param, args.value, args.db_user, args.db_name)
    print(msg)
    sys.exit(0 if ok else 1)
