# backend/app/integrations/prometheus.py
import logging
import threading

from cachetools import TTLCache, cached

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_metrics_cache: TTLCache = TTLCache(maxsize=1, ttl=10)
_metrics_cache_lock = threading.Lock()

_METRICS = {
    "cpu": "dummy_cpu_usage",
    "memory": "dummy_memory_usage",
    "request_count": "dummy_request_count",
}


def _query_metric(client: httpx.Client, metric_name: str) -> float | None:
    try:
        response = client.get(
            f"{settings.PROMETHEUS_URL}/api/v1/query",
            params={"query": metric_name},
            timeout=5,
        )
        response.raise_for_status()
        result = response.json()["data"]["result"]
        if result and len(result[0].get("value", [])) >= 2:
            return float(result[0]["value"][1])
        return None
    except Exception:
        logger.warning(
            "Failed to query Prometheus metric: %s", metric_name, exc_info=True
        )
        return None


@cached(cache=_metrics_cache, key=lambda: "metrics", lock=_metrics_cache_lock)
def get_current_metrics() -> dict:
    with httpx.Client() as client:
        return {
            key: _query_metric(client, metric_name)
            for key, metric_name in _METRICS.items()
        }


def get_metric_range(
    metric_name: str,
    hours: int = 24,
    step: str = "30m",
) -> list[tuple[float, float]]:
    """Prometheus range query. Returns [(unix_ts, value), ...] sorted by time."""
    import time as _time

    end = _time.time()
    start = end - hours * 3600
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{settings.PROMETHEUS_URL}/api/v1/query_range",
                params={"query": metric_name, "start": start, "end": end, "step": step},
                timeout=5,
            )
            response.raise_for_status()
            result = response.json()["data"]["result"]
            if result:
                return [(float(v[0]), float(v[1])) for v in result[0].get("values", [])]
    except Exception:
        logger.warning("Failed to query Prometheus range: %s", metric_name, exc_info=True)
    return []
