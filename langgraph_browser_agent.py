"""
LangGraph agent: Playwright-style UI step + API validation, with guardrails.

Run from repo root (must not be named ``agent.py`` — that would shadow the ``agent/`` package)::

    python langgraph_browser_agent.py

Imports use the top-level ``guardrails`` package and the ``agent`` *package* (directory).
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, NotRequired, TypedDict

import structlog
from langgraph.graph import END, StateGraph

from guardrails import create_guarded_agent_state
from guardrails.rate_limiter import RunLimits
from guardrails.retry_policy import TRANSIENT_HTTPX_ERRORS, with_retry

log = structlog.get_logger(__name__)


class BrowserApiAgentState(TypedDict, total=False):
    """State carried through Playwright + API validation; includes guardrail handles."""

    _run_limits: RunLimits
    _fallback_config: Any
    case_id: NotRequired[str]
    base_url: NotRequired[str]
    playwright_status: NotRequired[str]
    api_validation_status: NotRequired[str]
    rate_limit_summary: NotRequired[dict[str, int]]


def _emit_agentops_rate_limits(summary: dict[str, int]) -> None:
    """
    Emit final ``RunLimits`` counters for observability.

    Uses ``structlog`` with event name ``agentops_rate_limit_summary`` so AgentOps (or any
    JSON log sink) can index model/tool budget usage at graph completion without leaking
    case payload fields.
    """
    log.info("agentops_rate_limit_summary", **summary)


@with_retry(
    max_retries=3,
    backoff_factor=2.0,
    initial_delay=1.0,
    retry_on=(TimeoutError, ConnectionError),
    tool_name="playwright_execute",
)
async def playwright_execute_node(state: BrowserApiAgentState) -> BrowserApiAgentState:
    limits = state["_run_limits"]
    limits.check_and_increment_tool("playwright_execute")

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log.warning("playwright_not_installed", message="skipping browser step")
        return {**state, "playwright_status": "skipped_no_playwright"}

    base = state.get("base_url") or os.environ.get("FUNDING_UI_BASE", "about:blank")
    timeout_ms = int(os.environ.get("PLAYWRIGHT_TIMEOUT_MS", "30000"))

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(str(base), wait_until="domcontentloaded", timeout=timeout_ms)
            title = await page.title()
            log.info("playwright_step_ok", title=title)
            return {**state, "playwright_status": "ok"}
        finally:
            await browser.close()


@with_retry(
    max_retries=2,
    backoff_factor=2.0,
    initial_delay=0.5,
    retry_on=TRANSIENT_HTTPX_ERRORS,
    tool_name="api_validate",
)
async def api_validate_node(state: BrowserApiAgentState) -> BrowserApiAgentState:
    limits = state["_run_limits"]
    limits.check_and_increment_tool("api_validate")

    import httpx

    base = os.environ.get("FUNDING_API_BASE")
    if not base:
        log.warning("api_validate_skipped", reason="FUNDING_API_BASE unset")
        return {**state, "api_validation_status": "skipped_no_api_base"}

    url = f"{base.rstrip('/')}/cases"
    timeout = httpx.Timeout(10.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url)
        response.raise_for_status()
        status_code = response.status_code
    log.info("api_validate_ok", url=url, status_code=status_code)
    return {**state, "api_validation_status": "ok"}


def build_browser_api_graph() -> Any:
    graph = StateGraph(BrowserApiAgentState)
    graph.add_node("playwright_execute", playwright_execute_node)
    graph.add_node("api_validate", api_validate_node)
    graph.set_entry_point("playwright_execute")
    graph.add_edge("playwright_execute", "api_validate")
    graph.add_edge("api_validate", END)
    return graph.compile()


async def run_guarded_graph(raw_input: dict[str, Any]) -> BrowserApiAgentState:
    """
    (1) Run :func:`guardrails.create_guarded_agent_state` on ``raw_input`` before the graph.
    (2–3) Nodes use ``@with_retry`` and ``limits.check_and_increment_tool`` at the top.
    (4) Log ``limits.summary()`` for AgentOps at completion.
    """
    initial = create_guarded_agent_state(raw_input)
    limits = initial["_run_limits"]
    app = build_browser_api_graph()
    final: BrowserApiAgentState = await app.ainvoke(initial)
    summary = limits.summary()
    final = {**final, "rate_limit_summary": summary}
    _emit_agentops_rate_limits(summary)
    return final


async def _cli_async() -> None:
    raw: dict[str, Any] = {
        "case_id": os.environ.get("FUNDING_SEED_CASE_ID", ""),
        "base_url": os.environ.get("FUNDING_UI_BASE", "https://example.com"),
    }
    out = await run_guarded_graph(raw)
    log.info("agent_run_complete", rate_limit_summary=out.get("rate_limit_summary"))


if __name__ == "__main__":
    asyncio.run(_cli_async())
