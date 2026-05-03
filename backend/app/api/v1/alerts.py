# backend/app/api/v1/alerts.py
import asyncio
import logging
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from sqlalchemy import select

from app.ai.llm_analyzer import run_llm_pipeline
from app.db.session import SessionLocal, get_db
from app.models.alert_event import AlertEvent
from app.schemas.alert import AlertmanagerPayload
from app.schemas.incident import AlertEventRead
from app.services import incident_service
from app.services.incident_service import create_incident_from_llm_result

logger = logging.getLogger(__name__)

router = APIRouter()


def _run_llm_background(alert_event_ids: list[int]) -> None:
    db = SessionLocal()
    try:
        alert_events = list(
            db.execute(select(AlertEvent).where(AlertEvent.id.in_(alert_event_ids)))
            .scalars()
            .all()
        )
        if not alert_events:
            logger.warning("No alert events found for ids: %s", alert_event_ids)
            return
        start = time.perf_counter()
        analysis, action = asyncio.run(run_llm_pipeline(alert_events))
        create_incident_from_llm_result(alert_events, analysis, action, db)
        logger.info(
            "[TIMING] LLM background pipeline total completed in %.2fs",
            time.perf_counter() - start,
        )
    except Exception:
        logger.error("LLM background pipeline failed", exc_info=True)
    finally:
        db.close()


@router.post(
    "/alerts",
    response_model=list[AlertEventRead],
    status_code=status.HTTP_201_CREATED,
    summary="Alertmanager webhook",
    description="Receive Alertmanager webhook alerts and persist them.",
)
def receive_alert(
    payload: AlertmanagerPayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> list[AlertEventRead]:
    try:
        alert_events = incident_service.create_alert_events_from_payload(payload, db)
        background_tasks.add_task(_run_llm_background, [r.id for r in alert_events])
        return alert_events
    except Exception:
        logger.error("Failed to save alerts", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
