# backend/app/schemas/prediction.py
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.schema import MetricTypeEnum


class ForecastPoint(BaseModel):
    ds: datetime
    yhat: float
    yhat_lower: float
    yhat_upper: float


class ForecastResponse(BaseModel):
    metric: str
    full_name: str
    forecast: list[ForecastPoint]


class RiskAssessment(BaseModel):
    metric_type: str
    is_risky: bool
    severity: str
    peak_yhat: float
    expected_breach: Optional[datetime]
    confidence: float


class PredictionRead(BaseModel):
    id: int
    incident_id: Optional[int] = None
    target_node: str
    metric_type: MetricTypeEnum
    predicted_at: datetime
    expected_breach: Optional[datetime] = None
    confidence: Optional[float] = None
    is_verified: bool

    model_config = ConfigDict(from_attributes=True)
