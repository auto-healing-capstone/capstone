import threading
import time
import requests
import pandas as pd
from datetime import datetime, timedelta


PROMETHEUS_URL = "http://localhost:9090/api/v1/query_range"

COLLECTION_HOURS = {
    "cpu":          168,
    "memory":       168,
    "lt_memory":    24,
    "lt_disk":      72,
    "memory_leak":  0.5,  # 시뮬레이션 환경: 단기 트렌드 감지용 (운영 시 24로 복원)
    "fd_ratio":     0.5,
}

# §2 Prometheus 쿼리 최적화: 동일 주기 내 중복 조회 방지
_raw_cache: dict[str, tuple[list, float]] = {}
_raw_cache_lock = threading.Lock()
_RAW_CACHE_TTL = 60  # 60초 — 스케줄러 1회 실행 내 중복 쿼리 차단


def get_prometheus_data(metric_name: str, hours: int = 24):
    cache_key = f"{metric_name}:{hours}"

    # 캐시 HIT: 60초 이내 동일 쿼리는 재사용
    with _raw_cache_lock:
        entry = _raw_cache.get(cache_key)
        if entry is not None:
            data, expires_at = entry
            if time.monotonic() < expires_at:
                return data

    end_time   = datetime.now()
    start_time = end_time - timedelta(hours=hours)

    params = {
        "query": metric_name,
        "start": start_time.timestamp(),
        "end":   end_time.timestamp(),
        "step":  "1m",
    }

    try:
        response = requests.get(PROMETHEUS_URL, params=params, timeout=10)
        response.raise_for_status()
        results = response.json().get("data", {}).get("result", [])

        if not results:
            print(f"[Collector] 메트릭 '{metric_name}'에 대한 데이터가 Prometheus에 없습니다.")
            return []

        values = results[0].get("values", [])

        with _raw_cache_lock:
            _raw_cache[cache_key] = (values, time.monotonic() + _RAW_CACHE_TTL)

        return values

    except Exception as e:
        print(f"[Collector] 데이터 수집 중 오류 발생: {e}")
        return []
