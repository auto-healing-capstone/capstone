# backend/app/api/v1/alerts.py
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.alert import AlertmanagerPayload
from app.schemas.incident import AlertEventRead
from app.services import incident_service
from app.services.llm_service import run_llm_background
from app.schemas.alert import AlertFeedListResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/alerts",
    response_model=list[AlertEventRead],
    status_code=status.HTTP_201_CREATED,
    summary="Alertmanager webhook",
    description="Receive Alertmanager webhook alerts and persist them.",
)
def receive_alert(
    payload: AlertmanagerPayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> list[AlertEventRead]:
    if not payload.alerts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No alerts in payload",
        )
    try:
        alert_events = incident_service.create_alert_events_from_payload(payload, db)
        logger.info(
            "[TIMING] Alert received at %s", datetime.now(timezone.utc).isoformat()
        )
        background_tasks.add_task(run_llm_background, [r.id for r in alert_events])
        return alert_events
    except Exception:
        logger.error("Failed to persist alert events from payload", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get(
    "/alerts/feed",
    response_model=AlertFeedListResponse,
    status_code=status.HTTP_200_OK,
    summary="Alert feed for dashboard",
)
def get_alert_feed(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> AlertFeedListResponse:
    try:
        return incident_service.get_alert_feed(db, page=page, page_size=page_size)
    except Exception:
        logger.error("Failed to fetch alert feed", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
