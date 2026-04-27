"""
PostgreSQL DB 데드락 시뮬레이션.

docker exec psql 두 프로세스를 동시 실행해 교차 row-lock 을 유발하고
PostgreSQL 의 deadlock detected 에러를 반복 발생시킨 뒤 횟수를 상태 파일에 기록.

psycopg2 없이 psql 만 사용하므로 Windows 인코딩 문제 없음.

CLI:
  python simulate_deadlock.py --rounds 3
  python simulate_deadlock.py --rounds 5 --container aiops_postgres
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

DEFAULT_CONTAINER = os.getenv("POSTGRES_CONTAINER", "aiops_postgres")
DEFAULT_USER      = os.getenv("POSTGRES_USER",      "aiops_user")
DEFAULT_DB        = os.getenv("POSTGRES_DB",        "aiops_db")

SCENARIO_STATUS_FILE = os.getenv(
    "SCENARIO_STATUS_FILE", "/tmp/auto-healing-scenarios/status.json"
)

TABLE = "_deadlock_test"


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
# psql 헬퍼
# ---------------------------------------------------------------------------

def _psql_cmd(container: str, user: str, db: str) -> list[str]:
    return ["docker", "exec", "-i", container, "psql", "-U", user, "-d", db, "--no-psqlrc", "-q"]


def _psql(container: str, user: str, db: str, sql: str) -> tuple[bool, str]:
    """단일 SQL 문 실행."""
    try:
        r = subprocess.run(
            _psql_cmd(container, user, db),
            input=sql, capture_output=True, text=True, timeout=15,
        )
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return False, "psql timeout"
    except FileNotFoundError:
        return False, "docker CLI not found"


def _psql_stream(container: str, user: str, db: str, sql: str) -> tuple[int, str]:
    """SQL 스크립트를 stdin 으로 전달하고 (returncode, output) 반환."""
    try:
        r = subprocess.run(
            _psql_cmd(container, user, db),
            input=sql, capture_output=True, text=True, timeout=30,
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return -1, "timeout"
    except FileNotFoundError:
        return -1, "docker not found"


# ---------------------------------------------------------------------------
# 테스트 테이블 준비 / 정리
# ---------------------------------------------------------------------------

def _setup_table(container: str, user: str, db: str) -> tuple[bool, str]:
    sql = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (id SERIAL PRIMARY KEY, val TEXT);
DELETE FROM {TABLE};
INSERT INTO {TABLE} (val) VALUES ('row_A'), ('row_B');
"""
    return _psql(container, user, db, sql)


def _drop_table(container: str, user: str, db: str) -> None:
    _psql(container, user, db, f"DROP TABLE IF EXISTS {TABLE};")


# ---------------------------------------------------------------------------
# 단일 데드락 라운드
# ---------------------------------------------------------------------------
# Thread A: id=1 잠금 → 2초 대기 → id=2 잠금 시도 (B가 먼저 id=2 잡고 대기 중)
# Thread B: 0.5초 대기 → id=2 잠금 → id=1 잠금 시도 → DEADLOCK

_SQL_A = f"""
BEGIN;
SELECT id FROM {TABLE} WHERE id = 1 FOR UPDATE;
SELECT pg_sleep(2);
SELECT id FROM {TABLE} WHERE id = 2 FOR UPDATE;
ROLLBACK;
"""

_SQL_B = f"""
BEGIN;
SELECT pg_sleep(0.5);
SELECT id FROM {TABLE} WHERE id = 2 FOR UPDATE;
SELECT id FROM {TABLE} WHERE id = 1 FOR UPDATE;
ROLLBACK;
"""


def _run_thread(
    container: str, user: str, db: str,
    sql: str, results: list, idx: int,
) -> None:
    rc, output = _psql_stream(container, user, db, sql)
    if "deadlock detected" in output.lower() or "deadlock" in output.lower():
        results[idx] = "deadlock"
    elif rc == 0:
        results[idx] = "ok"
    else:
        results[idx] = f"error(rc={rc})"
    results[idx + 2] = output  # 디버그 출력 저장


# ---------------------------------------------------------------------------
# 공개 시뮬레이션 함수
# ---------------------------------------------------------------------------

def simulate_deadlock(
    rounds: int = 3,
    container: str = DEFAULT_CONTAINER,
    user: str = DEFAULT_USER,
    db: str = DEFAULT_DB,
) -> tuple[bool, str]:
    print(f"[1] DB 데드락 시뮬레이션 시작: container={container}, db={db}, rounds={rounds}")

    ok, msg = _setup_table(container, user, db)
    if not ok:
        return False, f"테이블 생성 실패: {msg}"
    print(f"[2] 테스트 테이블 '{TABLE}' 준비 완료")

    total_deadlocks = 0

    for round_num in range(1, rounds + 1):
        print(f"[3] 라운드 {round_num}/{rounds} 시작")
        # results: [result_A, result_B, output_A, output_B]
        results = [None, None, "", ""]

        t_a = threading.Thread(
            target=_run_thread,
            args=(container, user, db, _SQL_A, results, 0),
            daemon=True,
        )
        t_b = threading.Thread(
            target=_run_thread,
            args=(container, user, db, _SQL_B, results, 1),
            daemon=True,
        )
        t_a.start()
        t_b.start()
        t_a.join(timeout=30)
        t_b.join(timeout=30)

        round_deadlocks = results[:2].count("deadlock")
        total_deadlocks += round_deadlocks
        print(f"    A={results[0]}, B={results[1]} | round_dl={round_deadlocks}, total={total_deadlocks}")
        if round_deadlocks == 0:
            # 디버그 출력 표시
            print(f"    [A output] {results[2][:200]}")
            print(f"    [B output] {results[3][:200]}")
        _write_metric("db_deadlock_count", total_deadlocks)
        time.sleep(1)

    print(f"[4] 시뮬레이션 완료 - 총 데드락 횟수: {total_deadlocks}")

    _drop_table(container, user, db)
    print(f"[5] 테스트 테이블 '{TABLE}' 삭제 완료")

    _write_metric("db_deadlock_count", 0)
    return True, f"DB 데드락 시뮬레이션 완료 - 총 {total_deadlocks}회 데드락 발생"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PostgreSQL DB 데드락 시뮬레이션")
    p.add_argument("--rounds",    type=int, default=3,             help="데드락 반복 횟수")
    p.add_argument("--container", default=DEFAULT_CONTAINER,       help="PostgreSQL 컨테이너 이름")
    p.add_argument("--user",      default=DEFAULT_USER,            help="DB 사용자")
    p.add_argument("--db",        default=DEFAULT_DB,              help="DB 이름")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    ok, msg = simulate_deadlock(args.rounds, args.container, args.user, args.db)
    print(msg)
    sys.exit(0 if ok else 1)
