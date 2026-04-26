# backend/app/api/v1/predictions.py
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.db.session import get_db
from app.models.schema import MetricTypeEnum
from app.schemas.prediction import PredictionRead
from app.services import prediction_service

router = APIRouter()


@router.get(
    "/predictions",
    response_model=list[PredictionRead],
    status_code=http_status.HTTP_200_OK,
    summary="List predictions",
    description="Return prediction history with optional metric_type and target_node filters.",
)
def list_predictions(
    skip: int = Query(default=0, ge=0, description="Number of records to skip"),
    limit: int = Query(default=100, ge=1, le=500, description="Max records to return"),
    metric_type: Optional[MetricTypeEnum] = Query(
        default=None,
        description="Filter by metric type: CPU | MEMORY | DISK",
    ),
    target_node: Optional[str] = Query(
        default=None,
        description="Filter by target node name",
    ),
    db: Session = Depends(get_db),
) -> list[PredictionRead]:
    try:
        return prediction_service.get_predictions(
            db,
            skip=skip,
            limit=limit,
            metric_type=metric_type,
            target_node=target_node,
        )
    except Exception:
        logger.error("Failed to fetch predictions", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
