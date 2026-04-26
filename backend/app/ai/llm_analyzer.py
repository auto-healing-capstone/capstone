# backend/app/ai/llm_analyzer.py
import json
import logging
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat.chat_completion_message_tool_call import (
    ChatCompletionMessageToolCall,
)

from app.ai.function_tools import ANALYZE_TOOL, RECOMMEND_TOOL
from app.ai.prompts.analyze import ANALYZE_SYSTEM_PROMPT
from app.ai.prompts.recommend import RECOMMEND_SYSTEM_PROMPT
from app.core.config import settings
from app.models.alert_event import AlertEvent
from app.schemas.llm_action import ActionResult, AnalysisResult

_MODEL = "gpt-4o-mini"

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


def format_alert_events_for_llm(alerts: list[AlertEvent]) -> str:
    """Join multiple AlertEvents into numbered sections for LLM input."""
    sections = [
        f"[Alert {i}]\n{format_alert_event_for_llm(alert)}"
        for i, alert in enumerate(alerts, start=1)
    ]
    return "\n\n".join(sections)


async def _call_analyze(user_message: str) -> AnalysisResult:
    client = get_openai_client()
    response = await client.chat.completions.create(
        model=_MODEL,
        messages=[
            {"role": "system", "content": ANALYZE_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        tools=[ANALYZE_TOOL],
        tool_choice={"type": "function", "function": {"name": "analyze_incident"}},
    )
    tool_calls = response.choices[0].message.tool_calls
    if not tool_calls:
        raise RuntimeError("LLM returned no tool calls")
    if not isinstance(tool_calls[0], ChatCompletionMessageToolCall):
        raise RuntimeError(f"Unexpected tool call type: {type(tool_calls[0])}")
    args: dict[str, Any] = json.loads(tool_calls[0].function.arguments)
    return AnalysisResult(**args)


async def _call_recommend(analysis: AnalysisResult) -> ActionResult:
    client = get_openai_client()
    # Serialize Step 1 result so the model sees it as a prior tool call in context
    analysis_args = json.dumps(
        {
            "ai_title": analysis.ai_title,
            "ai_severity": analysis.ai_severity.value,
            "llm_analysis": analysis.llm_analysis,
        }
    )
    response = await client.chat.completions.create(
        model=_MODEL,
        messages=[
            {"role": "system", "content": RECOMMEND_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "Analyze this incident and recommend a recovery action.",
            },
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_analyze_0",
                        "type": "function",
                        "function": {
                            "name": "analyze_incident",
                            "arguments": analysis_args,
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "content": analysis_args,
                "tool_call_id": "call_analyze_0",
            },
        ],
        tools=[RECOMMEND_TOOL],
        tool_choice={"type": "function", "function": {"name": "recommend_action"}},
    )
    tool_calls = response.choices[0].message.tool_calls
    if not tool_calls:
        raise RuntimeError("LLM returned no tool calls")
    if not isinstance(tool_calls[0], ChatCompletionMessageToolCall):
        raise RuntimeError(f"Unexpected tool call type: {type(tool_calls[0])}")
    args: dict[str, Any] = json.loads(tool_calls[0].function.arguments)
    return ActionResult(**args)


async def run_llm_pipeline(
    alert_events: list[AlertEvent],
) -> tuple[AnalysisResult, ActionResult]:
    user_message = format_alert_events_for_llm(alert_events)
    analysis = await _call_analyze(user_message)
    action = await _call_recommend(analysis)
    return analysis, action
