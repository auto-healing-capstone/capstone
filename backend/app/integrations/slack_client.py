import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_SLACK_API_URL = "https://slack.com/api/chat.postMessage"


def send_approval_request(slack_summary: str) -> None:
    token = settings.SLACK_BOT_TOKEN
    channel = settings.SLACK_CHANNEL_ID

    if not token or not channel:
        logger.warning(
            "Slack notification skipped: SLACK_BOT_TOKEN or SLACK_CHANNEL_ID is not configured."
        )
        return

    text = (
        f"🚨 AIOps 복구 승인 요청\n{slack_summary}\n\n"
        "✅ 승인 또는 ❌ 거절 후 답장해주세요. (Week 5에서 버튼으로 대체 예정)"
    )

    response = httpx.post(
        _SLACK_API_URL,
        headers={"Authorization": f"Bearer {token}"},
        json={"channel": channel, "text": text},
    )

    if response.status_code != 200 or not response.json().get("ok"):
        logger.warning(
            "Slack API request failed: status=%s body=%s",
            response.status_code,
            response.text,
        )
