# backend/app/api/v1/slack.py
import json
import logging

from fastapi import APIRouter, Request

from app.db.session import SessionLocal
from app.services import healing_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/interactions")
async def slack_interactions(request: Request):
    try:
        form = await request.form()
        payload = json.loads(str(form["payload"]))
        action = payload["actions"][0]
        action_id = action["action_id"]
        recovery_action_id = int(action["value"])
    except Exception:
        logger.exception("Failed to parse Slack interaction payload")
        return {"text": "처리 완료"}

    db = SessionLocal()
    try:
        if action_id == "approve":
            healing_service.approve_recovery_action(
                recovery_action_id,
                reviewed_by="slack_user",
                reason="Slack 버튼 승인",
                db=db,
            )
        elif action_id == "reject":
            healing_service.reject_recovery_action(
                recovery_action_id,
                rejected_by="slack_user",
                reason="Slack 버튼 거절",
                db=db,
            )
    except Exception:
        logger.exception(
            "Failed to process Slack interaction for recovery_action_id=%d",
            recovery_action_id,
        )
    finally:
        db.close()

    return {"text": "처리 완료"}
