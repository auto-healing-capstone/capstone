# backend/app/services/prediction_service.py
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import requests
from sqlalchemy.orm import Session

from app.models.schema import (
    Incident,
    IncidentTypeEnum,
    MetricTypeEnum,
    Prediction,
    SeverityEnum,
    StatusEnum,
)
from app.schemas.prediction import ForecastResponse, RiskAssessment

logger = logging.getLogger(__name__)

PREDICTION_SERVER_URL = os.getenv("PREDICTION_SERVER_URL", "http://localhost:8001")
METRIC_TYPES = ["cpu", "memory", "disk"]

WARNING_THRESHOLD = 70.0
CRITICAL_THRESHOLD = 85.0


def fetch_forecast(metric_type: str) -> Optional[ForecastResponse]:
    url = f"{PREDICTION_SERVER_URL}/predict/forecast/{metric_type}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return ForecastResponse.model_validate(response.json())
    except requests.RequestException:
        logger.exception(
            "Failed to fetch forecast from prediction server: metric_type=%s",
            metric_type,
        )
    except Exception:
        logger.exception(
            "Failed to parse forecast response: metric_type=%s", metric_type
        )
    return None


def assess_risk(forecast: ForecastResponse, metric_type: str) -> RiskAssessment:
    points = forecast.forecast
    if points:
        peak_yhat = max(point.yhat for point in points)
    else:
        peak_yhat = 0.0

    if peak_yhat >= CRITICAL_THRESHOLD:
        severity = "CRITICAL"
        is_risky = True
        breach_threshold = CRITICAL_THRESHOLD
    elif peak_yhat >= WARNING_THRESHOLD:
        severity = "HIGH"
        is_risky = True
        breach_threshold = WARNING_THRESHOLD
    else:
        severity = "NONE"
        is_risky = False
        breach_threshold = None
    expected_breach = (
        next(
            (point.ds for point in points if point.yhat >= breach_threshold),
            None,
        )
        if breach_threshold is not None
        else None
    )

    if points:
        avg_interval_width = sum(
            (point.yhat_upper - point.yhat_lower) for point in points
        ) / len(points)
        confidence = max(0.0, 1 - (avg_interval_width / 100))
    else:
        confidence = 0.0

    return RiskAssessment(
        metric_type=metric_type,
        is_risky=is_risky,
        severity=severity,
        peak_yhat=peak_yhat,
        expected_breach=expected_breach,
        confidence=confidence,
    )


def save_prediction(assessment: RiskAssessment, db: Session) -> Prediction:
    prediction = Prediction(
        target_node="system",
        metric_type=MetricTypeEnum[assessment.metric_type.upper()],
        predicted_at=datetime.now(timezone.utc),
        expected_breach=assessment.expected_breach,
        confidence=assessment.confidence,
        is_verified=False,
        incident_id=None,
    )
    db.add(prediction)
    db.flush()
    return prediction


# 주의: is_risky=True일 때만 호출할 것
# severity가 NONE이면 SeverityEnum KeyError 발생
def save_proactive_incident(
    assessment: RiskAssessment,
    prediction: Prediction,
    db: Session,
) -> Incident:
    incident_type_map = {
        "cpu": IncidentTypeEnum.HIGH_CPU,
        "memory": IncidentTypeEnum.OOM,
        "disk": IncidentTypeEnum.DISK_FULL,
    }

    incident = Incident(
        incident_types=[incident_type_map[assessment.metric_type.lower()]],
        trigger_metrics={
            "peak_yhat": assessment.peak_yhat,
            "threshold": WARNING_THRESHOLD,
            "metric_type": assessment.metric_type,
        },
        target_node="system",
        status=StatusEnum.DETECTED,
        ai_severity=SeverityEnum[assessment.severity],
        ai_title=f"{assessment.metric_type.upper()} 리소스 임계값 초과 예측",
    )

    db.add(incident)
    db.flush()

    prediction.incident_id = incident.id
    return incident


def run_prediction_job(db: Session) -> None:
    try:
        for metric_type in METRIC_TYPES:
            forecast = fetch_forecast(metric_type)
            if forecast is None:
                continue

            assessment = assess_risk(forecast, metric_type)
            prediction = save_prediction(assessment, db)

            if assessment.is_risky:
                save_proactive_incident(assessment, prediction, db)

        db.commit()
    except Exception:
        logger.exception("Prediction job failed")
        db.rollback()
