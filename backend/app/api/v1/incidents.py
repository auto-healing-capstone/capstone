# backend/app/api/v1/incidents.py
from typing import Optional

from fastapi import APIRouter, Query, status

from app.schemas.incident import IncidentRead
from app.services import incident_service

router = APIRouter()


@router.get(
    "/incidents",
    response_model=list[IncidentRead],
    status_code=status.HTTP_200_OK,
    summary="List incidents",
    description="Return incident history with optional status filter.",
)
def list_incidents(
    skip: int = Query(default=0, ge=0, description="Number of records to skip"),
    limit: int = Query(default=100, ge=1, le=500, description="Max records to return"),
    status: Optional[str] = Query(
        default=None,
        pattern="^(firing|resolved)$",
        description="Status filter: firing | resolved",
    ),
) -> list[IncidentRead]:
    return incident_service.get_dummy_incidents(status=status)


# try:
#     return incident_service.get_incidents(
#         db, skip=skip, limit=limit, status=status
#     )
# except Exception as exc:
#     raise HTTPException(
#         status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#         detail=f"Failed to fetch incidents: {exc}",
#     )
