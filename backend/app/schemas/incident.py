# backend/app/schemas/incident.py
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.schema import IncidentTypeEnum, SeverityEnum, StatusEnum

__all__ = ["AlertEventRead", "IncidentRead"]


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


class AlertEventRead(IncidentBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class IncidentRead(BaseModel):
    id: int
    target_node: str
    status: StatusEnum
    ai_title: Optional[str] = None
    ai_severity: Optional[SeverityEnum] = None
    incident_types: list[IncidentTypeEnum]
    trigger_metrics: Optional[dict] = None
    llm_analysis: Optional[dict] = None
    detected_at: datetime
    resolved_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
