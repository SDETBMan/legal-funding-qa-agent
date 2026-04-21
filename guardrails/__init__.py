"""
Local guardrails package (PII, rate limits, retry policy).

``create_guarded_agent_state`` is the canonical preprocessing entry for LangGraph runs.
"""

from __future__ import annotations

from typing import Any

import structlog

from guardrails.pii_redactor import get_default_pii_redactor
from guardrails.rate_limiter import RunLimits
from guardrails.retry_policy import FallbackModelConfig
from guardrails.summarization_middleware import SummarizationMiddleware
from guardrails.tool_selector_middleware import ToolSelectorMiddleware, ToolSpec

log = structlog.get_logger(__name__)

fallback_config = FallbackModelConfig(
    primary="claude-sonnet-4-6",
    fallback="gpt-4.1",
)


def create_guarded_agent_state(raw_input: dict[str, Any]) -> dict[str, Any]:
    """
    Preprocess all inputs before ``invoke`` / ``ainvoke``:

    1. Redact string fields in ``raw_input`` (Presidio).
    2. Attach a fresh :class:`~guardrails.rate_limiter.RunLimits` on ``_run_limits``.
    3. Attach ``fallback_config`` on ``_fallback_config``.
    """
    redactor = get_default_pii_redactor()
    sanitized = redactor.redact_dict(dict(raw_input))
    limits = RunLimits(model_call_limit=50, tool_call_limit=200)
    return {
        **sanitized,
        "_run_limits": limits,
        "_fallback_config": fallback_config,
    }


def prepare_langgraph_invoke(raw_input: dict[str, Any]) -> tuple[dict[str, Any], RunLimits]:
    """Same as :func:`create_guarded_agent_state` but pops ``_run_limits`` for graph-closure wiring."""
    guarded = create_guarded_agent_state(raw_input)
    limits = guarded.pop("_run_limits")
    if not isinstance(limits, RunLimits):
        raise TypeError("create_guarded_agent_state must set _run_limits to RunLimits")
    log.debug(
        "guardrails_prepared",
        keys=list(guarded.keys()),
        rate_limits=limits.summary(),
    )
    return guarded, limits


__all__ = [
    "create_guarded_agent_state",
    "fallback_config",
    "prepare_langgraph_invoke",
    "FallbackModelConfig",
    "RunLimits",
    "SummarizationMiddleware",
    "ToolSelectorMiddleware",
    "ToolSpec",
]
