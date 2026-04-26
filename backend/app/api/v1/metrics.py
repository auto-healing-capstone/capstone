# backend/app/api/v1/metrics.py
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi import status as http_status

from app.integrations.prometheus import get_current_metrics
from app.schemas.metrics import CurrentMetricsResponse

router = APIRouter()


@router.get(
    "/metrics/current",
    response_model=CurrentMetricsResponse,
    status_code=http_status.HTTP_200_OK,
    summary="Current system metrics",
    description="Return the latest CPU, memory, and request count from Prometheus.",
)
def get_metrics_current() -> CurrentMetricsResponse:
    try:
        data = get_current_metrics()
        return CurrentMetricsResponse(
            **data,
            collected_at=datetime.now(timezone.utc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch metrics: {exc}",
        )
