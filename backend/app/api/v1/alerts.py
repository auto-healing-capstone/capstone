# backend/app/api/v1/alerts.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.alert import AlertmanagerPayload
from app.schemas.incident import IncidentRead
from app.services import incident_service

router = APIRouter()


@router.post(
    "/alerts",
    response_model=list[IncidentRead],
    status_code=status.HTTP_201_CREATED,
    summary="Alertmanager webhook",
    description="Receive Alertmanager webhook alerts and persist them.",
)
def receive_alert(
    payload: AlertmanagerPayload,
    db: Session = Depends(get_db),
) -> list[IncidentRead]:
    try:
        return incident_service.create_alert_events_from_payload(payload, db)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save alerts: {exc}",
        )
