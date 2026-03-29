# backend/app/services/incident_service.py
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alert_event import AlertEvent
from app.schemas.alert import AlertmanagerPayload, SingleAlert
from app.schemas.incident import IncidentRead


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
) -> list[IncidentRead]:
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

    return [IncidentRead.model_validate(i) for i in saved]


def _find_existing_by_fingerprint(
    fingerprint: Optional[str],
    db: Session,
) -> Optional[AlertEvent]:
    if not fingerprint:
        return None

    stmt = (
        select(AlertEvent)
        .where(AlertEvent.fingerprint == fingerprint)
        .where(AlertEvent.status == "firing")  # 진행 중인 것만 업데이트 대상
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
    status: Optional[str] = None,
) -> list[IncidentRead]:
    stmt = select(AlertEvent)
    if status:
        stmt = stmt.where(AlertEvent.status == status)
    stmt = stmt.order_by(AlertEvent.starts_at.desc()).offset(skip).limit(limit)
    alert_events = list(db.execute(stmt).scalars().all())
    return [IncidentRead.model_validate(e) for e in alert_events]  # ORM → Pydantic 변환


def get_dummy_incidents(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
) -> list[IncidentRead]:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    all_incidents = [
        IncidentRead(
            id=1,
            alert_name="HighCPU",
            severity="critical",
            status="firing",
            instance="server-01",
            summary="CPU usage over 90%",
            description="CPU has been over 90% for 5 minutes.",
            fingerprint="fp_001",
            starts_at=now,
            ends_at=None,
            created_at=now,
        ),
        IncidentRead(
            id=2,
            alert_name="DiskFull",
            severity="warning",
            status="resolved",
            instance="server-02",
            summary="Disk usage over 85%",
            description="Disk /dev/sda1 is 87% full.",
            fingerprint="fp_002",
            starts_at=now,
            ends_at=now,
            created_at=now,
        ),
    ]

    if status:
        all_incidents = [i for i in all_incidents if i.status == status]

    return all_incidents[skip : skip + limit]
