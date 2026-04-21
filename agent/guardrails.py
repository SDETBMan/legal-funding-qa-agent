"""
Compatibility shim: canonical guardrails live in the top-level :mod:`guardrails` package.
"""

from __future__ import annotations

from guardrails import (
    create_guarded_agent_state,
    fallback_config,
    prepare_langgraph_invoke,
)

__all__ = ["create_guarded_agent_state", "fallback_config", "prepare_langgraph_invoke"]
