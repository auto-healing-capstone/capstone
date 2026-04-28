# backend/app/services/incident_service.py
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.events import broadcaster
from app.integrations.slack_client import send_approval_request
from app.models.alert_event import AlertEvent
from app.models.schema import (
    ApprovalStatusEnum,
    Incident,
    RecoveryAction,
    StatusEnum,
)
from app.schemas.alert import AlertmanagerPayload, SingleAlert
from app.schemas.incident import AlertEventRead, IncidentRead
from app.schemas.llm_action import ActionResult, AnalysisResult
from app.schemas.recovery_action import RecoveryActionRead

logger = logging.getLogger(__name__)

_ALERT_STATUS_FIRING = "firing"


def _alert_to_orm(alert: SingleAlert) -> AlertEvent:
    return AlertEvent(
        alert_name=alert.alert_name,
        severity=alert.severity,
        status=alert.status,
        instance=alert.labels.get("instance"),
        summary=alert.annotations.get("summary"),
        description=alert.annotations.get("description"),
        fingerprint=alert.fingerprint,
        starts_at=alert.startsAt,
        ends_at=alert.endsAt,
    )


def create_alert_events_from_payload(
    payload: AlertmanagerPayload,
    db: Session,
) -> list[AlertEventRead]:
    saved: list[AlertEvent] = []

    for alert in payload.alerts:
        existing = _find_existing_by_fingerprint(alert.fingerprint, db)

        if existing:
            _update_alert_event(existing, alert)
            saved.append(existing)
        else:
            new_incident = _alert_to_orm(alert)
            db.add(new_incident)
            saved.append(new_incident)

    db.commit()

    for incident in saved:
        db.refresh(incident)

    return [AlertEventRead.model_validate(i) for i in saved]


def _find_existing_by_fingerprint(
    fingerprint: Optional[str],
    db: Session,
) -> Optional[AlertEvent]:
    if not fingerprint:
        return None

    stmt = (
        select(AlertEvent)
        .where(AlertEvent.fingerprint == fingerprint)
        .where(
            AlertEvent.status == _ALERT_STATUS_FIRING
        )  # 진행 중인 것만 업데이트 대상
        .order_by(AlertEvent.starts_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def _update_alert_event(
    existing: AlertEvent,
    alert: SingleAlert,
) -> None:
    existing.status = alert.status
    existing.ends_at = alert.endsAt
    existing.summary = alert.annotations.get("summary")
    existing.description = alert.annotations.get("description")


def get_incidents(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    status: Optional[StatusEnum] = None,
) -> list[IncidentRead]:
    stmt = select(Incident).order_by(Incident.detected_at.desc())
    if status:
        stmt = stmt.where(Incident.status == status)
    stmt = stmt.offset(skip).limit(limit)
    incidents = list(db.execute(stmt).scalars().all())
    return [IncidentRead.model_validate(i) for i in incidents]


def get_alert_events(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    incident_id: Optional[int] = None,
) -> list[AlertEventRead]:
    stmt = select(AlertEvent).order_by(AlertEvent.starts_at.desc())
    if status:
        stmt = stmt.where(AlertEvent.status == status)
    if incident_id is not None:
        stmt = stmt.where(AlertEvent.incident_id == incident_id)
    stmt = stmt.offset(skip).limit(limit)
    alert_events = list(db.execute(stmt).scalars().all())
    return [AlertEventRead.model_validate(e) for e in alert_events]


def create_incident_from_llm_result(
    alert_events: list[AlertEvent],
    analysis: AnalysisResult,
    action: ActionResult,
    db: Session,
) -> None:
    trigger_metrics = {
        "alerts": [
            {
                "alert_name": ae.alert_name,
                "severity": ae.severity,
                "status": ae.status,
                "instance": ae.instance,
                "summary": ae.summary,
                "description": ae.description,
                "fingerprint": ae.fingerprint,
                "starts_at": ae.starts_at.isoformat(),
                "ends_at": ae.ends_at.isoformat() if ae.ends_at else None,
            }
            for ae in alert_events
        ]
    }

    incident = Incident(
        incident_types=analysis.incident_types,
        trigger_metrics=trigger_metrics,
        target_node=alert_events[0].instance or "unknown",
        status=StatusEnum.PENDING,
        ai_title=analysis.ai_title,
        ai_severity=analysis.ai_severity,
        llm_analysis={"analysis": analysis.llm_analysis},
    )
    try:
        db.add(incident)
        db.flush()

        for ae in alert_events:
            ae.incident_id = incident.id

        recovery_action = RecoveryAction(
            incident_id=incident.id,
            action_type=action.action_type,
            approval_status=ApprovalStatusEnum.PENDING,
            params=action.params,
        )
        db.add(recovery_action)
        db.commit()
    except Exception:
        db.rollback()
        logger.error("Incident creation transaction failed", exc_info=True)
        raise

    try:
        broadcaster.broadcast(
            "new_incident",
            {
                "incident_id": incident.id,
                "ai_title": incident.ai_title,
                "ai_severity": (
                    incident.ai_severity.value if incident.ai_severity else None
                ),
                "status": incident.status.value,
            },
        )
    except Exception:
        logger.warning("SSE broadcast new_incident failed", exc_info=True)

    try:
        send_approval_request(action.slack_summary)
    except Exception:
        logger.warning("Slack approval request failed", exc_info=True)


def get_incident(incident_id: int, db: Session) -> IncidentRead:
    incident = db.execute(
        select(Incident).where(Incident.id == incident_id)
    ).scalar_one_or_none()
    if incident is None:
        raise ValueError(f"Incident not found: id={incident_id}")
    return IncidentRead.model_validate(incident)


def get_incident_recovery_actions(
    incident_id: int, db: Session
) -> list[RecoveryActionRead]:
    rows = list(
        db.execute(
            select(RecoveryAction)
            .where(RecoveryAction.incident_id == incident_id)
            .order_by(RecoveryAction.id.desc())
        )
        .scalars()
        .all()
    )
    return [RecoveryActionRead.model_validate(r) for r in rows]
