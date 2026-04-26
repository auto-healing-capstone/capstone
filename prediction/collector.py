import requests
import time
import pandas as pd
from datetime import datetime, timedelta


def get_prometheus_data(metric_name="dummy_cpu_usage", hours=24):
    base_url = "http://localhost:9090/api/v1/query_range"

    end_time = time.time()
    start_time = end_time - (hours * 3600)

    params = {"query": metric_name, "start": start_time, "end": end_time, "step": "1m"}

    response = requests.get(base_url, params=params, timeout=10)
    data = response.json()

    results = data.get("data", {}).get("result", [])
    if not results:
        return []
    return results[0]["values"]
