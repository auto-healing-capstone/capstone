# backend/app/services/prediction_job.py
# Group A 전용 예측 잡 — prediction_service.py 를 건드리지 않고 독립 동작
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
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

METRIC_TYPES = [
    "memory_leak",
    "fd_ratio",
]

_watch_counter: dict[str, int] = {m: 0 for m in METRIC_TYPES}
_WATCH_INCIDENT_THRESHOLD = 3

# §3 Circuit Breaker: 예측 서버 연속 장애 시 연쇄 장애 방지
_failure_counts: dict[str, int] = {m: 0 for m in METRIC_TYPES}
_circuit_open_until: dict[str, float] = {m: 0.0 for m in METRIC_TYPES}
_CIRCUIT_FAILURE_THRESHOLD = 3
_CIRCUIT_RESET_SECONDS = 300

_LEVEL_TO_SEVERITY: dict[str, tuple[str, bool]] = {
    "CRITICAL": ("CRITICAL", True),
    "WARNING": ("HIGH", True),
    "WATCH": ("MEDIUM", False),
    "CLEAR": ("NONE", False),
    "UNKNOWN": ("NONE", False),
}

_METRIC_ENUM_MAP: dict[str, MetricTypeEnum] = {
    "memory_leak": MetricTypeEnum.MEMORY_LEAK,
    "fd_ratio": MetricTypeEnum.FD_RATIO,
}

_INCIDENT_TYPE_MAP: dict[str, IncidentTypeEnum] = {
    "memory_leak": IncidentTypeEnum.MEMORY_LEAK,
    "fd_ratio": IncidentTypeEnum.FD_EXHAUSTION,
}


def fetch_forecast(metric_type: str) -> Optional[ForecastResponse]:
    if time.monotonic() < _circuit_open_until.get(metric_type, 0.0):
        logger.warning(
            "Circuit breaker OPEN for %s — skipping fetch (retry after %.0fs)",
            metric_type,
            _circuit_open_until[metric_type] - time.monotonic(),
        )
        return None

    url = f"{settings.PREDICTION_SERVER_URL}/predict/forecast/{metric_type}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        _failure_counts[metric_type] = 0
        _circuit_open_until[metric_type] = 0.0
        return ForecastResponse.model_validate(response.json())
    except requests.RequestException:
        _failure_counts[metric_type] = _failure_counts.get(metric_type, 0) + 1
        if _failure_counts[metric_type] >= _CIRCUIT_FAILURE_THRESHOLD:
            _circuit_open_until[metric_type] = time.monotonic() + _CIRCUIT_RESET_SECONDS
            logger.error(
                "Circuit breaker OPENED for %s after %d consecutive failures",
                metric_type,
                _failure_counts[metric_type],
            )
        else:
            logger.exception("Failed to fetch forecast: metric_type=%s", metric_type)
    except Exception:
        logger.exception(
            "Failed to parse forecast response: metric_type=%s", metric_type
        )
    return None


def assess_risk(forecast: ForecastResponse, metric_type: str) -> RiskAssessment:
    severity, is_risky = _LEVEL_TO_SEVERITY.get(forecast.anomaly_level, ("NONE", False))
    peak_yhat = forecast.peak_predicted or 0.0
    confidence = max(0.0, 1.0 - (forecast.anomaly_score or 0.0))

    expected_breach: Optional[datetime] = None
    if forecast.breach_time and is_risky:
        try:
            h, m = map(int, forecast.breach_time.split(":"))
            now = datetime.now(timezone.utc)
            candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if candidate < now:
                candidate += timedelta(days=1)
            expected_breach = candidate
        except Exception:
            pass

    return RiskAssessment(
        metric_type=metric_type,
        is_risky=is_risky,
        severity=severity,
        peak_yhat=peak_yhat,
        expected_breach=expected_breach,
        confidence=confidence,
        anomaly_level=forecast.anomaly_level,
        reason=forecast.reason,
        recommended_action=forecast.recommended_action,
        breach_duration_min=forecast.breach_duration_min,
    )


def _has_active_incident(metric_type: str, db: Session) -> bool:
    metric_enum = _METRIC_ENUM_MAP.get(metric_type)
    if metric_enum is None:
        return False

    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    stmt = (
        select(Prediction)
        .where(Prediction.metric_type == metric_enum)
        .where(Prediction.incident_id.is_not(None))
        .where(Prediction.predicted_at >= cutoff)
    )
    return db.execute(stmt).first() is not None


def save_prediction(assessment: RiskAssessment, db: Session) -> Prediction:
    metric_enum = _METRIC_ENUM_MAP.get(assessment.metric_type.lower())
    if metric_enum is None:
        raise ValueError(f"Unknown metric_type: {assessment.metric_type}")

    prediction = Prediction(
        target_node="system",
        metric_type=metric_enum,
        predicted_at=datetime.now(timezone.utc),
        expected_breach=assessment.expected_breach,
        confidence=assessment.confidence,
        is_verified=False,
        incident_id=None,
    )
    db.add(prediction)
    db.flush()
    return prediction


def save_proactive_incident(
    assessment: RiskAssessment,
    prediction: Prediction,
    db: Session,
) -> Incident:
    incident_type = _INCIDENT_TYPE_MAP.get(assessment.metric_type.lower())
    if incident_type is None:
        raise ValueError(f"Unknown metric_type: {assessment.metric_type}")

    try:
        severity = SeverityEnum[assessment.severity]
    except KeyError:
        raise ValueError(f"Unknown severity: {assessment.severity}")

    incident = Incident(
        incident_types=[incident_type],
        trigger_metrics={
            "peak_yhat": assessment.peak_yhat,
            "metric_type": assessment.metric_type,
            "anomaly_level": assessment.anomaly_level,
            "reason": assessment.reason,
            "recommended_action": assessment.recommended_action,
            "breach_duration_min": assessment.breach_duration_min,
        },
        target_node="system",
        status=StatusEnum.DETECTED,
        ai_severity=severity,
        ai_title=(
            f"[{assessment.anomaly_level}] "
            f"{assessment.metric_type.upper()} 이상 징후 예측"
        ),
    )
    db.add(incident)
    db.flush()
    prediction.incident_id = incident.id
    return incident


def verify_past_predictions(db: Session) -> None:
    stmt = (
        select(Prediction)
        .join(Incident, Prediction.incident_id == Incident.id)
        .where(Incident.status == StatusEnum.RESOLVED)
        .where(Prediction.is_verified == False)  # noqa: E712
    )
    rows = list(db.execute(stmt).scalars())
    for pred in rows:
        pred.is_verified = True
    if rows:
        logger.info("Verified %d predictions linked to RESOLVED incidents", len(rows))


def run_prediction_job(db: Session) -> None:
    try:
        for metric_type in METRIC_TYPES:
            forecast = fetch_forecast(metric_type)
            if forecast is None:
                logger.warning("No forecast for %s", metric_type)
                continue

            if forecast.anomaly_level == "UNKNOWN":
                logger.info("Skipping %s: data insufficient", metric_type)
                continue

            assessment = assess_risk(forecast, metric_type)
            prediction = save_prediction(assessment, db)

            level = forecast.anomaly_level
            if level == "WATCH":
                _watch_counter[metric_type] = _watch_counter.get(metric_type, 0) + 1
                logger.info(
                    "WATCH count for %s: %d/%d",
                    metric_type,
                    _watch_counter[metric_type],
                    _WATCH_INCIDENT_THRESHOLD,
                )
            elif level in ("CLEAR", "UNKNOWN"):
                if _watch_counter.get(metric_type, 0) > 0:
                    logger.info(
                        "WATCH counter reset for %s (level=%s)", metric_type, level
                    )
                _watch_counter[metric_type] = 0

            watch_triggered = (
                level == "WATCH"
                and _watch_counter.get(metric_type, 0) >= _WATCH_INCIDENT_THRESHOLD
            )
            should_create_incident = assessment.is_risky or watch_triggered

            if should_create_incident:
                if _has_active_incident(metric_type, db):
                    logger.info(
                        "Skipping incident creation for %s: active incident exists",
                        metric_type,
                    )
                else:
                    if watch_triggered and not assessment.is_risky:
                        assessment = assessment.model_copy(
                            update={"severity": "MEDIUM", "is_risky": True}
                        )
                    incident = save_proactive_incident(assessment, prediction, db)
                    logger.info(
                        "Created incident %s for %s [%s]%s",
                        incident.id,
                        metric_type,
                        assessment.anomaly_level,
                        " (WATCH x3)" if watch_triggered else "",
                    )
                    if watch_triggered:
                        _watch_counter[metric_type] = 0

        verify_past_predictions(db)
        db.commit()
    except Exception:
        logger.exception("Group A prediction job failed")
        db.rollback()
