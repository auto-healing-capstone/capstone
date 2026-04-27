"""
PostgreSQL 커넥션 풀 고갈 시뮬레이션.

max_connections 이상의 연결을 동시에 열어 고갈 상태를 유발하고
활성 연결 수를 시나리오 상태 파일에 기록해 Prometheus가 감지하게 함.

CLI:
  python simulate_connection_pool.py --connections 20 --duration 30
  python simulate_connection_pool.py --connections 5 --duration 10 --host localhost

주의: DB의 max_connections가 낮을수록 (예: 5~10) 고갈이 빨리 발생합니다.
      .env의 POSTGRES_MAX_CONNECTIONS를 낮게 설정 후 테스트하세요.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

try:
    import psycopg2
except ImportError:
    print("psycopg2가 설치되어 있지 않습니다: pip install psycopg2-binary", file=sys.stderr)
    sys.exit(1)

DEFAULT_HOST = os.getenv("POSTGRES_HOST", "localhost")
DEFAULT_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
DEFAULT_USER = os.getenv("POSTGRES_USER", "postgres")
DEFAULT_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
DEFAULT_DB = os.getenv("POSTGRES_DB", "postgres")

SCENARIO_STATUS_FILE = os.getenv(
    "SCENARIO_STATUS_FILE", "/tmp/auto-healing-scenarios/status.json"
)


def _write_metric(db_active: int, db_max: int) -> None:
    path = Path(SCENARIO_STATUS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(path.read_text()) if path.exists() else {}
    except (json.JSONDecodeError, OSError):
        data = {}
    data["db_active_connections"] = db_active
    data["db_max_connections"] = db_max
    data["updated_at"] = int(time.time())
    path.write_text(json.dumps(data))


def _open_conn(host, port, user, password, db):
    try:
        return psycopg2.connect(
            host=host, port=port, user=user,
            password=password, dbname=db,
            connect_timeout=5,
        )
    except psycopg2.OperationalError:
        return None


def _query_max_connections(conn) -> int:
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW max_connections;")
            return int(cur.fetchone()[0])
    except Exception:
        return 0


def simulate_connection_pool(
    connections: int = 20,
    duration: int = 30,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    user: str = DEFAULT_USER,
    password: str = DEFAULT_PASSWORD,
    db: str = DEFAULT_DB,
) -> tuple[bool, str]:
    print(f"[1] {connections}개 연결 동시 오픈 시도 (DB: {host}:{port}/{db})")

    active: list = []
    failed = 0
    max_conn = 0

    for i in range(connections):
        conn = _open_conn(host, port, user, password, db)
        if conn:
            if max_conn == 0:
                max_conn = _query_max_connections(conn)
            active.append(conn)
            print(f"  연결 {i+1:3d}: 성공  (활성 {len(active)}개)")
        else:
            failed += 1
            print(f"  연결 {i+1:3d}: 실패  ← max_connections 초과")
        _write_metric(len(active), max_conn)

    print(f"\n[2] 상태: 활성 {len(active)}개 / 실패 {failed}개 / max_connections {max_conn}")
    if failed > 0:
        print("  ✓ 커넥션 풀 고갈 확인됨")

    print(f"[3] {duration}초 유지 중...")
    time.sleep(duration)

    print(f"[4] 모든 연결 해제")
    for conn in active:
        try:
            conn.close()
        except Exception:
            pass

    _write_metric(0, max_conn)
    success = len(active) > 0
    return success, f"커넥션 풀 시뮬레이션 완료: 활성 {len(active)}개, 실패 {failed}개"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PostgreSQL 커넥션 풀 고갈 시뮬레이션")
    p.add_argument("--connections", type=int, default=20, help="동시 연결 시도 수")
    p.add_argument("--duration", type=int, default=30, help="연결 유지 시간(초)")
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--user", default=DEFAULT_USER)
    p.add_argument("--password", default=DEFAULT_PASSWORD)
    p.add_argument("--db", default=DEFAULT_DB)
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    ok, msg = simulate_connection_pool(
        args.connections, args.duration,
        args.host, args.port, args.user, args.password, args.db,
    )
    print(msg)
    sys.exit(0 if ok else 1)
