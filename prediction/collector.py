import requests
import time
import pandas as pd
from datetime import datetime, timedelta


PROMETHEUS_URL = "http://localhost:9090/api/v1/query_range"

def get_prometheus_data(metric_name: str, hours: int = 24):
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours)

    params = {
        "query": metric_name,
        "start": start_time.timestamp(),
        "end": end_time.timestamp(),
        "step": "1m"
    }

    try:
        response = requests.get(PROMETHEUS_URL, params=params, timeout=10)
        response.raise_for_status()
        results = response.json().get("data", {}).get("result", [])

        if not results:
            print(f"[Collector] 메트릭 '{metric_name}'에 대한 데이터가 Prometheus에 없습니다.")
            return []

        return results[0].get("values", [])

    except Exception as e:
        print(f"[Collector] 데이터 수집 중 오류 발생: {e}")
        return []