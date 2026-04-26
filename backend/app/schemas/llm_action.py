# app/schemas/llm_action.py
from app.models.schema import ActionTypeEnum, IncidentTypeEnum, SeverityEnum
from pydantic import BaseModel


class AnalysisResult(BaseModel):
    ai_title: str
    ai_severity: SeverityEnum
    llm_analysis: str
    incident_types: list[IncidentTypeEnum]


class ActionResult(BaseModel):
    action_type: ActionTypeEnum
    reason: str
    slack_summary: str
