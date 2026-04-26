# backend/app/api/v1/alert_events.py
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.incident import AlertEventRead
from app.services import incident_service

router = APIRouter()


@router.get(
    "/alert-events",
    response_model=list[AlertEventRead],
    status_code=http_status.HTTP_200_OK,
    summary="List alert events",
    description="Return raw alert events with optional status and incident_id filters.",
)
def list_alert_events(
    skip: int = Query(default=0, ge=0, description="Number of records to skip"),
    limit: int = Query(default=100, ge=1, le=500, description="Max records to return"),
    status: Optional[str] = Query(
        default=None,
        pattern="^(firing|resolved)$",
        description="Status filter: firing | resolved",
    ),
    incident_id: Optional[int] = Query(
        default=None,
        description="Filter by linked incident ID",
    ),
    db: Session = Depends(get_db),
) -> list[AlertEventRead]:
    try:
        return incident_service.get_alert_events(
            db,
            skip=skip,
            limit=limit,
            status=status,
            incident_id=incident_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch alert events: {exc}",
        )
