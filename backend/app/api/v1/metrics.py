# backend/app/api/v1/metrics.py
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi import status as http_status

from app.integrations.prometheus import get_current_metrics, get_metric_range
from app.schemas.metrics import ChartPoint, CurrentMetricsResponse, MetricCardItem

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/metrics/current",
    response_model=CurrentMetricsResponse,
    status_code=http_status.HTTP_200_OK,
    summary="Current system metrics",
)
def get_metrics_current() -> CurrentMetricsResponse:
    try:
        data = get_current_metrics()
        return CurrentMetricsResponse(
            **data,
            collected_at=datetime.now(timezone.utc),
        )
    except Exception:
        logger.error("Failed to fetch metrics", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get(
    "/metrics/cards",
    response_model=list[MetricCardItem],
    status_code=http_status.HTTP_200_OK,
    summary="Metric summary cards",
)
def get_metrics_cards() -> list[MetricCardItem]:
    try:
        current = get_current_metrics()
        cpu_series = get_metric_range("dummy_cpu_usage", hours=1, step="5m")
        mem_series = get_metric_range("dummy_memory_usage", hours=1, step="5m")

        def _trend(series: list[tuple[float, float]]) -> tuple[str, str]:
            if len(series) < 2:
                return "steady", "0%"
            prev, curr = series[-2][1], series[-1][1]
            if prev == 0:
                return "steady", "0%"
            pct = (curr - prev) / prev * 100
            if pct > 1:
                return "up", f"+{pct:.1f}%"
            if pct < -1:
                return "down", f"{pct:.1f}%"
            return "steady", f"{pct:+.1f}%"

        cpu_trend, cpu_change = _trend(cpu_series)
        mem_trend, mem_change = _trend(mem_series)

        return [
            MetricCardItem(
                key="cpu",
                label="CPU Usage",
                value=round(current.get("cpu") or 0.0, 1),
                unit="%",
                change=cpu_change,
                trend=cpu_trend,
            ),
            MetricCardItem(
                key="memory",
                label="Memory Usage",
                value=round(current.get("memory") or 0.0, 1),
                unit="%",
                change=mem_change,
                trend=mem_trend,
            ),
            MetricCardItem(
                key="disk",
                label="Disk Usage",
                value=0.0,
                unit="%",
                change="0%",
                trend="steady",
            ),
        ]
    except Exception:
        logger.error("Failed to fetch metric cards", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get(
    "/metrics/chart",
    response_model=list[ChartPoint],
    status_code=http_status.HTTP_200_OK,
    summary="Metric time-series for chart",
)
def get_metrics_chart() -> list[ChartPoint]:
    try:
        cpu_series = get_metric_range("dummy_cpu_usage", hours=24, step="30m")
        mem_series = get_metric_range("dummy_memory_usage", hours=24, step="30m")

        # bucket size 30 min
        bucket = 1800
        points: dict[int, dict] = {}

        for ts, val in cpu_series:
            key = int(ts / bucket) * bucket
            if key not in points:
                points[key] = {
                    "time": datetime.fromtimestamp(key, tz=timezone.utc).isoformat(),
                    "cpu": 0.0,
                    "memory": 0.0,
                    "disk": 0.0,
                }
            points[key]["cpu"] = round(val, 1)

        for ts, val in mem_series:
            key = int(ts / bucket) * bucket
            if key not in points:
                points[key] = {
                    "time": datetime.fromtimestamp(key, tz=timezone.utc).isoformat(),
                    "cpu": 0.0,
                    "memory": 0.0,
                    "disk": 0.0,
                }
            points[key]["memory"] = round(val, 1)

        return [ChartPoint(**p) for p in sorted(points.values(), key=lambda x: x["time"])]
    except Exception:
        logger.error("Failed to fetch metric chart", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
