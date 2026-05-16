# backend/app/services/prediction_service.py
import asyncio
import logging
import math
import threading
from datetime import datetime, timezone
from typing import Any, Optional

import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.ai.llm_analyzer import run_llm_pipeline_from_message
from app.core.config import settings
from app.core.events import broadcaster
from app.db.session import SessionLocal
from app.integrations.slack_client import send_approval_request
from app.models.schema import (
    ActionTypeEnum,
    ApprovalStatusEnum,
    Incident,
    IncidentTypeEnum,
    MetricTypeEnum,
    Prediction,
    RecoveryAction,
    SeverityEnum,
    StatusEnum,
)
from app.schemas.llm_action import ActionResult, AnalysisResult
from app.schemas.prediction import (
    ForecastResponse,
    PredictionListResponse,
    PredictionRead,
    RiskAssessment,
)

logger = logging.getLogger(__name__)

METRIC_TYPES = ["cpu", "memory", "disk"]

WARNING_THRESHOLD = 70.0
CRITICAL_THRESHOLD = 85.0


def fetch_forecast(metric_type: str) -> Optional[ForecastResponse]:
    url = f"{settings.PREDICTION_SERVER_URL}/predict/forecast/{metric_type}"
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

    incident_type = incident_type_map.get(assessment.metric_type.lower())
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
            "threshold": WARNING_THRESHOLD,
            "metric_type": assessment.metric_type,
        },
        target_node="system",
        status=StatusEnum.DETECTED,
        ai_severity=severity,
        ai_title=f"{assessment.metric_type.upper()} 리소스 임계값 초과 예측",
    )

    db.add(incident)
    db.flush()

    prediction.incident_id = incident.id
    return incident


def get_predictions(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    metric_type: Optional[MetricTypeEnum] = None,
    target_node: Optional[str] = None,
) -> PredictionListResponse:
    base_stmt = select(Prediction)
    if metric_type:
        base_stmt = base_stmt.where(Prediction.metric_type == metric_type)
    if target_node:
        base_stmt = base_stmt.where(Prediction.target_node == target_node)

    total = db.execute(
        select(func.count()).select_from(base_stmt.subquery())
    ).scalar_one()
    total_pages = max(1, math.ceil(total / page_size))

    stmt = base_stmt.order_by(Prediction.predicted_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    predictions = list(db.execute(stmt).scalars().all())

    return PredictionListResponse(
        items=[PredictionRead.model_validate(p) for p in predictions],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


def _fallback_for_proactive(incident: Incident) -> tuple[AnalysisResult, ActionResult]:
    trigger = incident.trigger_metrics or {}
    metric_type = trigger.get("metric_type", "").lower()
    incident_types: list[IncidentTypeEnum] = list(
        incident.incident_types or [IncidentTypeEnum.HIGH_CPU]
    )
    incident_type = incident_types[0]

    if metric_type == "cpu":
        action_type = ActionTypeEnum.SCALE_OUT
        params: dict[str, Any] = {"cpu_quota": 50000}
    elif metric_type == "memory":
        action_type = ActionTypeEnum.RESTART_CONTAINER
        params = {}
    elif metric_type == "disk":
        action_type = ActionTypeEnum.CLEAR_LOGS
        params = {}
    else:
        action_type = ActionTypeEnum.RESTART_CONTAINER
        params = {}

    analysis = AnalysisResult(
        ai_title=incident.ai_title or f"[Fallback] {metric_type.upper()} 예측",
        ai_severity=incident.ai_severity or SeverityEnum.HIGH,
        llm_analysis="LLM unavailable. Rule-based fallback applied.",
        incident_types=incident_types,
    )
    action = ActionResult(
        action_type=action_type,
        reason="LLM fallback: rule-based selection",
        slack_summary=(
            f"[Fallback] {incident_type.value} predicted."
            f" Applying {action_type.value}."
        ),
        params=params,
    )
    return analysis, action


async def run_llm_pipeline_for_incident(
    incident: Incident,
) -> tuple[AnalysisResult, ActionResult]:
    trigger = incident.trigger_metrics or {}
    if incident.ai_severity is not None:
        severity_str = incident.ai_severity.value
    else:
        severity_str = "UNKNOWN"
    user_message = (
        f"Proactive Incident (Prediction-based)\n"
        f"Metric Type: {trigger.get('metric_type', 'unknown')}\n"
        f"Peak Predicted Value: {trigger.get('peak_yhat', 0):.1f}%\n"
        f"Threshold: {trigger.get('threshold', 0)}%\n"
        f"Incident Type: {', '.join(t.value for t in incident.incident_types or [])}\n"
        f"Severity: {severity_str}\n"
        f"Title: {incident.ai_title or 'N/A'}"
    )
    try:
        analysis, action = await run_llm_pipeline_from_message(user_message)
    except Exception as exc:
        logger.error(
            "LLM pipeline for proactive incident %d failed: %s",
            incident.id,
            exc,
            exc_info=True,
        )
        return _fallback_for_proactive(incident)
    return analysis, action


def _run_proactive_llm_background(incident_id: int) -> None:
    db = SessionLocal()
    try:
        incident = db.execute(
            select(Incident).where(Incident.id == incident_id)
        ).scalar_one_or_none()
        if incident is None:
            logger.warning("Proactive incident not found: id=%d", incident_id)
            return

        analysis, action = asyncio.run(run_llm_pipeline_for_incident(incident))

        incident.status = StatusEnum.PENDING
        incident.ai_title = analysis.ai_title
        incident.ai_severity = analysis.ai_severity
        incident.llm_analysis = {"analysis": analysis.llm_analysis}

        recovery_action = RecoveryAction(
            incident_id=incident.id,
            action_type=action.action_type,
            approval_status=ApprovalStatusEnum.PENDING,
            params=action.params,
        )
        db.add(recovery_action)
        db.commit()

        try:
            _severity = incident.ai_severity
            if _severity is not None:
                ai_severity_value = _severity.value
            else:
                ai_severity_value = None
            broadcaster.broadcast(
                "new_incident",
                {
                    "incident_id": incident.id,
                    "ai_title": incident.ai_title,
                    "ai_severity": ai_severity_value,
                    "status": incident.status.value,
                },
            )
        except Exception:
            logger.warning("SSE broadcast new_incident failed", exc_info=True)

        try:
            send_approval_request(action.slack_summary, recovery_action.id)
        except Exception:
            logger.warning("Slack approval request failed", exc_info=True)

    except Exception:
        logger.error(
            "Proactive LLM background failed for incident_id=%d",
            incident_id,
            exc_info=True,
        )
        db.rollback()
    finally:
        db.close()


def run_prediction_job(db: Session) -> None:
    proactive_incident_ids: list[int] = []
    try:
        for metric_type in METRIC_TYPES:
            forecast = fetch_forecast(metric_type)
            if forecast is None:
                continue

            assessment = assess_risk(forecast, metric_type)
            prediction = save_prediction(assessment, db)

            if assessment.is_risky:
                incident = save_proactive_incident(assessment, prediction, db)
                proactive_incident_ids.append(incident.id)

        db.commit()
    except Exception:
        logger.exception("Prediction job failed")
        db.rollback()
        return

    for incident_id in proactive_incident_ids:
        threading.Thread(
            target=_run_proactive_llm_background,
            args=(incident_id,),
            daemon=True,
        ).start()
