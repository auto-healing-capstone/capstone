# backend/app/schemas/incident.py
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class IncidentBase(BaseModel):
    alert_name: str
    severity: str
    status: str
    instance: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    fingerprint: Optional[str] = None
    starts_at: datetime
    ends_at: Optional[datetime] = None
    incident_id: Optional[int] = None


class IncidentCreate(IncidentBase):
    pass


class IncidentRead(IncidentBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
