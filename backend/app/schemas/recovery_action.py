# backend/app/schemas/recovery_action.py
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.schema import ActionTypeEnum, ApprovalStatusEnum


class RecoveryActionRead(BaseModel):
    id: int
    incident_id: Optional[int] = None
    prediction_id: Optional[int] = None
    action_type: ActionTypeEnum
    params: Optional[dict] = None
    approval_status: ApprovalStatusEnum
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    executed_at: Optional[datetime] = None
    is_successful: Optional[bool] = None
    log_snippet: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class RecoveryActionListResponse(BaseModel):
    items: list[RecoveryActionRead]
    page: int
    page_size: int
    total: int
    total_pages: int


class ApproveRequest(BaseModel):
    reviewed_by: str
    reason: Optional[str] = None


class RejectRequest(BaseModel):
    rejected_by: str
    reason: Optional[str] = None


class HealRequest(BaseModel):
    recovery_action_id: int
