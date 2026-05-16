# backend/app/services/llm_service.py
import asyncio
import logging
import time

from sqlalchemy import select

from app.ai.llm_analyzer import run_llm_pipeline
from app.db.session import SessionLocal
from app.models.alert_event import AlertEvent
from app.services.incident_service import create_incident_from_llm_result

logger = logging.getLogger(__name__)


def run_llm_background(alert_event_ids: list[int]) -> None:
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
        try:
            analysis, action = asyncio.run(run_llm_pipeline(alert_events))
            create_incident_from_llm_result(alert_events, analysis, action, db)
        except Exception:
            logger.error(
                "LLM pipeline failed for alert_event_ids=%s",
                alert_event_ids,
                exc_info=True,
            )
            return
        logger.info(
            "[TIMING] LLM background pipeline total completed in %.2fs",
            time.perf_counter() - start,
        )
    except Exception:
        logger.error("Failed to fetch alert events from DB", exc_info=True)
    finally:
        db.close()
