# backend/app/api/v1/incidents.py
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.schema import StatusEnum
from app.schemas.incident import IncidentRead
from app.schemas.recovery_action import RecoveryActionRead
from app.services import incident_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/incidents",
    response_model=list[IncidentRead],
    status_code=http_status.HTTP_200_OK,
    summary="List incidents",
    description="Return incident history with optional status filter.",
)
def list_incidents(
    skip: int = Query(default=0, ge=0, description="Number of records to skip"),
    limit: int = Query(default=100, ge=1, le=500, description="Max records to return"),
    status: Optional[StatusEnum] = Query(
        default=None,
        description=(
            "Status filter: DETECTED | ANALYZING | PENDING "
            "| RECOVERING | RESOLVED | FAILED"
        ),
    ),
    db: Session = Depends(get_db),
) -> list[IncidentRead]:
    try:
        return incident_service.get_incidents(db, skip=skip, limit=limit, status=status)
    except Exception:
        logger.error("Failed to fetch incidents", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get(
    "/incidents/{incident_id}",
    response_model=IncidentRead,
    status_code=http_status.HTTP_200_OK,
    summary="Get incident",
    description="Return a single incident by ID.",
)
def get_incident(
    incident_id: int,
    db: Session = Depends(get_db),
) -> IncidentRead:
    try:
        return incident_service.get_incident(incident_id, db)
    except ValueError:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Incident not found: id={incident_id}",
        )
    except Exception:
        logger.error("Failed to fetch incident id=%s", incident_id, exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get(
    "/incidents/{incident_id}/recovery-actions",
    response_model=list[RecoveryActionRead],
    status_code=http_status.HTTP_200_OK,
    summary="List recovery actions for an incident",
    description="Return all recovery actions linked to the given incident, newest first.",
)
def list_incident_recovery_actions(
    incident_id: int,
    db: Session = Depends(get_db),
) -> list[RecoveryActionRead]:
    try:
        return incident_service.get_incident_recovery_actions(incident_id, db)
    except Exception:
        logger.error(
            "Failed to fetch recovery actions for incident id=%s",
            incident_id,
            exc_info=True,
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
