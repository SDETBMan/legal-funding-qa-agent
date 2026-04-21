"""Run-level rate limits for LangGraph nodes (LLM and tool call budgets)."""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

log = structlog.get_logger(__name__)


class RateLimitExceeded(Exception):
    """Raised when an agent exceeds its configured call budget for a run."""


@dataclass
class RunLimits:
    """
    Per-run call budget. Scope to one compiled graph invocation unless you call ``reset``.

    Tune for CI: cap model roundtrips and tool executions (Playwright, HTTP, etc.)
    so runaway loops fail fast without exhausting API budget or blocking the queue.
    """

    model_call_limit: int = 50
    tool_call_limit: int = 200
    model_calls: int = field(default=0, init=False)
    tool_calls: int = field(default=0, init=False)

    def reset(self) -> None:
        """Clear counters so the same instance can bound a new invoke on a reused graph."""
        self.model_calls = 0
        self.tool_calls = 0

    def check_and_increment_model(self, node_name: str = "unknown") -> None:
        """Call before each LLM roundtrip; raises ``RateLimitExceeded`` if over budget."""
        self.model_calls += 1
        if self.model_calls > self.model_call_limit:
            log.error(
                "model_call_limit_exceeded",
                node=node_name,
                model_calls=self.model_calls,
                model_call_limit=self.model_call_limit,
            )
            raise RateLimitExceeded(
                f"Model call limit of {self.model_call_limit} exceeded "
                f"(current: {self.model_calls}) in node {node_name!r}. "
                "Increase the limit or inspect an agent loop."
            )
        log.debug(
            "model_call_tick",
            node=node_name,
            model_calls=self.model_calls,
            model_call_limit=self.model_call_limit,
        )

    def check_and_increment_tool(self, tool_name: str = "unknown") -> None:
        """Call before each tool execution (browser, HTTP client, etc.)."""
        self.tool_calls += 1
        if self.tool_calls > self.tool_call_limit:
            log.error(
                "tool_call_limit_exceeded",
                tool=tool_name,
                tool_calls=self.tool_calls,
                tool_call_limit=self.tool_call_limit,
            )
            raise RateLimitExceeded(
                f"Tool call limit of {self.tool_call_limit} exceeded "
                f"(current: {self.tool_calls}) for tool {tool_name!r}. "
                "Increase the limit or inspect an agent loop."
            )
        log.debug(
            "tool_call_tick",
            tool=tool_name,
            tool_calls=self.tool_calls,
            tool_call_limit=self.tool_call_limit,
        )

    def summary(self) -> dict[str, int]:
        """Metrics for AgentOps / CI artifacts (no secrets)."""
        return {
            "model_calls": self.model_calls,
            "model_call_limit": self.model_call_limit,
            "model_calls_remaining": max(0, self.model_call_limit - self.model_calls),
            "tool_calls": self.tool_calls,
            "tool_call_limit": self.tool_call_limit,
            "tool_calls_remaining": max(0, self.tool_call_limit - self.tool_calls),
        }
