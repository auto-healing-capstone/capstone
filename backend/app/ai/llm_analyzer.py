# backend/app/ai/llm_analyzer.py
import json
import logging
import time
from typing import Any

import openai
from openai import AsyncOpenAI
from openai.types.chat.chat_completion_message_tool_call import (
    ChatCompletionMessageToolCall,
)
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.ai.function_tools import ANALYZE_TOOL, RECOMMEND_TOOL
from app.ai.prompts.analyze import ANALYZE_SYSTEM_PROMPT
from app.ai.prompts.recommend import RECOMMEND_SYSTEM_PROMPT
from app.core.config import settings
from app.models.alert_event import AlertEvent
from app.models.schema import ActionTypeEnum, IncidentTypeEnum, SeverityEnum
from app.schemas.llm_action import ActionResult, AnalysisResult

_MODEL = "gpt-4o-mini"

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None
_client_key: str | None = None  # tracks the key used to build _client


def _is_valid_api_key(key: str | None) -> bool:
    return bool(key and key.startswith("sk-"))


def get_openai_client() -> AsyncOpenAI:
    """Return the shared AsyncOpenAI client, reinitializing if the key changed."""
    global _client, _client_key
    key = settings.OPENAI_API_KEY
    effective_key = key if _is_valid_api_key(key) else None

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


def _log_retry(retry_state) -> None:
    logger.warning(
        "LLM API retrying (attempt %d): %s",
        retry_state.attempt_number,
        retry_state.outcome.exception(),
    )


@retry(
    retry=retry_if_exception_type(
        (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError)
    ),
    wait=wait_exponential(multiplier=1, min=1, max=16),
    stop=stop_after_attempt(3),
    before_sleep=_log_retry,
)
async def _call_analyze(user_message: str) -> AnalysisResult:
    start = time.perf_counter()
    client = get_openai_client()
    try:
        response = await client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": ANALYZE_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            tools=[ANALYZE_TOOL],
            tool_choice={"type": "function", "function": {"name": "analyze_incident"}},
            timeout=30.0,
        )
    except (openai.AuthenticationError, openai.BadRequestError):
        raise
    tool_calls = response.choices[0].message.tool_calls
    if not tool_calls:
        raise RuntimeError("LLM returned no tool calls")
    if not isinstance(tool_calls[0], ChatCompletionMessageToolCall):
        raise RuntimeError(f"Unexpected tool call type: {type(tool_calls[0])}")
    args: dict[str, Any] = json.loads(tool_calls[0].function.arguments)
    logger.info(
        "[TIMING] LLM Step1 analyze completed in %.2fs", time.perf_counter() - start
    )
    return AnalysisResult(**args)


@retry(
    retry=retry_if_exception_type(
        (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError)
    ),
    wait=wait_exponential(multiplier=1, min=1, max=16),
    stop=stop_after_attempt(3),
    before_sleep=_log_retry,
)
async def _call_recommend(analysis: AnalysisResult) -> ActionResult:
    start = time.perf_counter()
    client = get_openai_client()
    # Serialize Step 1 result so the model sees it as a prior tool call in context
    analysis_args = json.dumps(
        {
            "ai_title": analysis.ai_title,
            "ai_severity": analysis.ai_severity.value,
            "llm_analysis": analysis.llm_analysis,
        }
    )
    try:
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
            timeout=30.0,
        )
    except (openai.AuthenticationError, openai.BadRequestError):
        raise
    tool_calls = response.choices[0].message.tool_calls
    if not tool_calls:
        raise RuntimeError("LLM returned no tool calls")
    if not isinstance(tool_calls[0], ChatCompletionMessageToolCall):
        raise RuntimeError(f"Unexpected tool call type: {type(tool_calls[0])}")
    args: dict[str, Any] = json.loads(tool_calls[0].function.arguments)
    logger.info(
        "[TIMING] LLM Step2 recommend completed in %.2fs", time.perf_counter() - start
    )
    return ActionResult(**args)


def _fallback_pipeline(
    alert_events: list[AlertEvent],
) -> tuple[AnalysisResult, ActionResult]:
    alert_name = alert_events[0].alert_name if alert_events else "unknown"
    name_lower = alert_name.lower()

    if "cpu" in name_lower:
        incident_type = IncidentTypeEnum.HIGH_CPU
        action_type = ActionTypeEnum.SCALE_OUT
        params: dict[str, Any] = {"cpu_quota": 50000}
    elif "mem" in name_lower or "oom" in name_lower:
        incident_type = IncidentTypeEnum.OOM
        action_type = ActionTypeEnum.RESTART_CONTAINER
        params = {}
    elif "disk" in name_lower:
        incident_type = IncidentTypeEnum.DISK_FULL
        action_type = ActionTypeEnum.CLEAR_LOGS
        params = {}
    elif "nginx" in name_lower:
        incident_type = IncidentTypeEnum.NGINX_5XX
        action_type = ActionTypeEnum.RESTART_PROCESS
        params = {"process": "nginx"}
    else:
        incident_type = IncidentTypeEnum.HIGH_CPU
        action_type = ActionTypeEnum.RESTART_CONTAINER
        params = {}

    analysis = AnalysisResult(
        ai_title=f"[Fallback] {alert_name}",
        ai_severity=SeverityEnum.HIGH,
        llm_analysis="LLM unavailable. Rule-based fallback applied.",
        incident_types=[incident_type],
    )
    action = ActionResult(
        action_type=action_type,
        reason="LLM fallback: rule-based selection",
        slack_summary=f"[Fallback] {incident_type} detected. Applying {action_type}.",
        params=params,
    )
    return analysis, action


async def run_llm_pipeline(
    alert_events: list[AlertEvent],
) -> tuple[AnalysisResult, ActionResult]:
    start = time.perf_counter()
    user_message = format_alert_events_for_llm(alert_events)
    try:
        analysis = await _call_analyze(user_message)
        action = await _call_recommend(analysis)
    except (RetryError, Exception) as exc:
        logger.error(
            "LLM pipeline failed, applying rule-based fallback: %s", exc
        )
        return _fallback_pipeline(alert_events)
    logger.info(
        "[TIMING] LLM pipeline total completed in %.2fs", time.perf_counter() - start
    )
    return analysis, action
