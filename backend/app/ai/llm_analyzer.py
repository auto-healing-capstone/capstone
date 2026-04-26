import logging

from openai import AsyncOpenAI

from app.core.config import settings
from app.models.alert_event import AlertEvent

logger = logging.getLogger(__name__)

_PLACEHOLDER = "sk-your-openai-api-key-here"

_client: AsyncOpenAI | None = None
_client_key: str | None = None  # tracks the key used to build _client


def get_openai_client() -> AsyncOpenAI:
    """Return the shared AsyncOpenAI client, reinitializing if the key changed."""
    global _client, _client_key
    key = settings.OPENAI_API_KEY
    effective_key = key if (key and key != _PLACEHOLDER) else None

    # Reinitialize when a real key becomes available after a NOT_SET initialization
    if _client is not None and _client_key is None and effective_key is not None:
        logger.info("OPENAI_API_KEY is now set; reinitializing OpenAI client.")
        _client = None

    if _client is None:
        if effective_key is None:
            logger.warning(
                "OPENAI_API_KEY is not configured. "
                "Set it in .env before calling LLM endpoints."
            )
        _client = AsyncOpenAI(api_key=effective_key or "NOT_SET")
        _client_key = effective_key
    return _client


def format_alert_event_for_llm(alert: AlertEvent) -> str:
    """Convert AlertEvent to formatted text for LLM analysis."""
    lines = [
        f"Alert Name: {alert.alert_name}",
        f"Severity: {alert.severity}",
        f"Status: {alert.status}",
    ]

    if alert.instance:
        lines.append(f"Instance: {alert.instance}")

    if alert.summary:
        lines.append(f"Summary: {alert.summary}")

    if alert.description:
        lines.append(f"Description: {alert.description}")

    lines.append(f"Started At: {alert.starts_at.isoformat()}")

    if alert.ends_at:
        lines.append(f"Ended At: {alert.ends_at.isoformat()}")

    return "\n".join(lines)
