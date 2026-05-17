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
    anomaly_level: str = "UNKNOWN"
    full_name: Optional[str] = None
    threshold: Optional[float] = None
    anomaly_score: Optional[float] = None
    reason: Optional[str] = None
    breach_time: Optional[str] = None  # "HH:MM" 형식
    breach_duration_min: Optional[int] = None
    recommended_action: Optional[str] = None
    forecast: list[ForecastPoint] = []
    peak_predicted: Optional[float] = None
    llm_context: Optional[str] = None


class RiskAssessment(BaseModel):
    metric_type: str
    is_risky: bool
    severity: str
    peak_yhat: float
    expected_breach: Optional[datetime]
    confidence: float
    anomaly_level: str = "UNKNOWN"
    reason: Optional[str] = None
    recommended_action: Optional[str] = None
    breach_duration_min: Optional[int] = None


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


class PredictionListResponse(BaseModel):
    items: list[PredictionRead]
    page: int
    page_size: int
    total: int
    total_pages: int
