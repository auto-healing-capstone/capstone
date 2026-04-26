# backend/app/api/v1/incidents.py
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.schema import StatusEnum
from app.schemas.incident import IncidentRead
from app.services import incident_service

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
        description="Status filter: DETECTED | ANALYZING | PENDING | RECOVERING | RESOLVED | FAILED",
    ),
    db: Session = Depends(get_db),
) -> list[IncidentRead]:
    try:
        return incident_service.get_incidents(db, skip=skip, limit=limit, status=status)
    except Exception as exc:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch incidents: {exc}",
        )
