# backend/app/api/v1/predictions.py
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.schema import MetricTypeEnum
from app.schemas.prediction import PredictionListResponse
from app.services import prediction_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/predictions",
    response_model=PredictionListResponse,
    status_code=http_status.HTTP_200_OK,
    summary="List predictions",
    description=(
        "Return prediction history with optional metric_type and target_node filters."
    ),
)
def list_predictions(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Page size"),
    metric_type: Optional[MetricTypeEnum] = Query(
        default=None,
        description="Filter by metric type: CPU | MEMORY | DISK",
    ),
    target_node: Optional[str] = Query(
        default=None,
        description="Filter by target node name",
    ),
    db: Session = Depends(get_db),
) -> PredictionListResponse:
    try:
        return prediction_service.get_predictions(
            db,
            page=page,
            page_size=page_size,
            metric_type=metric_type,
            target_node=target_node,
        )
    except Exception:
        logger.error("Failed to fetch predictions", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
