# backend/app/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler

from app.db.session import SessionLocal
from app.services import healing_service, prediction_service

scheduler = None


def scheduled_prediction_job() -> None:
    db = SessionLocal()
    try:
        prediction_service.run_prediction_job(db)
    finally:
        db.close()


def scheduled_expire_job() -> None:
    db = SessionLocal()
    try:
        healing_service.expire_pending_actions(db)
    finally:
        db.close()


def create_scheduler() -> BackgroundScheduler:
    global scheduler

    if scheduler is None or not scheduler.running:
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            scheduled_prediction_job,
            trigger="interval",
            minutes=5,
            id="prediction_job",
            replace_existing=True,
        )
        scheduler.add_job(
            scheduled_expire_job,
            trigger="interval",
            minutes=5,
            id="expire_job",
            replace_existing=True,
        )

    return scheduler
