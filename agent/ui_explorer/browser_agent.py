from __future__ import annotations

from typing import Any

from playwright.async_api import Page
from pydantic import BaseModel, ConfigDict

class PageState(BaseModel):
    """INV-13–INV-16: Structured perception input for LLM browser decisions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    url: str
    title: str
    accessibility_snapshot: str
    screenshot_b64: str | None = None

class BrowserAction(BaseModel):
    """INV-13–INV-16: Next action in the perception-action loop."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    payload: dict[str, Any]

class ActionResult(BaseModel):
    """INV-13–INV-16: Outcome of executing a BrowserAction on the page."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool
    detail: str

class BrowserRunResult(BaseModel):
    """INV-13–INV-16: Termination state for a browser-use goal run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    goal: str
    status: str
    steps: int

class BrowserAgent:
    """
    LLM-driven Playwright agent for UI exploration (§7, §3).

    Targets UI consistency invariants INV-13, INV-14, INV-15, and INV-16.
    """

    async def run(self, goal: str) -> BrowserRunResult:
        """INV-13–INV-16: Run until goal_reached, max_steps, or unrecoverable_error."""
        raise NotImplementedError

    async def _perceive(self, page: Page) -> PageState:
        """INV-13–INV-16: Snapshot accessibility tree, screenshot, URL, and title."""
        raise NotImplementedError

    async def _decide(self, state: PageState, goal: str) -> BrowserAction:
        """INV-13–INV-16: LLM chooses next click | fill | navigate | assert | report_bug."""
        raise NotImplementedError

    async def _act(self, page: Page, action: BrowserAction) -> ActionResult:
        """INV-13–INV-16: Execute the decided action against the live page."""
        raise NotImplementedError
