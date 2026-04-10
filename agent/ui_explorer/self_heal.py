from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from playwright.async_api import Page

class SelectorRepairProposal(BaseModel):
    """INV-13–INV-16: Human-reviewable selector change; never silent trust violation (§7.2)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    broken_selector: str
    proposed_selector: str
    rationale: str

class SelectorHealer:
    """
    Propose selector repairs when UI structure drifts (§7.2).

    Supports reliable checks for INV-13, INV-14, INV-15, and INV-16 after UI changes.
    """

    async def attempt_repair(self, broken_selector: str, page: Page) -> SelectorRepairProposal:
        """INV-13–INV-16: Find semantic equivalent and emit a logged, reviewable proposal."""
        raise NotImplementedError
