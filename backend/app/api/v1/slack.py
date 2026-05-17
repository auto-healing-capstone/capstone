# backend/app/api/v1/slack.py
import json
import logging

import httpx
from fastapi import APIRouter, Request

from app.core.config import settings
from app.db.session import SessionLocal
from app.services import healing_service

_SLACK_API_URL = "https://slack.com/api/chat.postMessage"

logger = logging.getLogger(__name__)


def _send_slack_text(text: str) -> None:
    try:
        response = httpx.post(
            _SLACK_API_URL,
            headers={"Authorization": f"Bearer {settings.SLACK_BOT_TOKEN}"},
            json={"channel": settings.SLACK_CHANNEL_ID, "text": text},
        )
        if response.status_code != 200 or not response.json().get("ok"):
            logger.warning(
                "Slack notify failed: status=%s body=%s",
                response.status_code,
                response.text,
            )
    except Exception:
        logger.warning("Slack notify failed", exc_info=True)


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
            _send_slack_text(
                f"✅ 승인되었습니다. 복구를 실행합니다.\n액션 ID: {recovery_action_id}"
            )
            try:
                healing_service.execute_recovery(recovery_action_id, db)
            except Exception:
                logger.exception(
                    "execute_recovery failed for recovery_action_id=%d",
                    recovery_action_id,
                )
        elif action_id == "reject":
            healing_service.reject_recovery_action(
                recovery_action_id,
                rejected_by="slack_user",
                reason="Slack 버튼 거절",
                db=db,
            )
            _send_slack_text(f"❌ 거절되었습니다.\n액션 ID: {recovery_action_id}")
    except Exception:
        logger.exception(
            "Failed to process Slack interaction for recovery_action_id=%d",
            recovery_action_id,
        )
    finally:
        db.close()

    return {"text": "처리 완료"}
