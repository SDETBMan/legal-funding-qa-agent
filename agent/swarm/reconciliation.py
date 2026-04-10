from __future__ import annotations

from typing import Any

from agent.clients.funding_client import FundingClient
from agent.ui_explorer.browser_agent import BrowserAgent

# INV-13, INV-15: Registered natural-language goals for UI↔API financial reconciliation.
RECONCILIATION_GOALS: list[str] = []

class ReconciliationVerifier:
    """
    UI-to-API financial reconciliation for the release gate (§11.2).

    INV-13: Payoff shown in UI must match API payoff to the cent.
    INV-15: Waterfall preview in UI must match API-computed waterfall.
    """

    def __init__(self, funding: FundingClient, browser: BrowserAgent) -> None:
        self._funding = funding
        self._browser = browser

    async def verify_funding_payoff(self, funding_id: str) -> dict[str, Any]:
        """INV-13: Compare API payoff cents to UI-extracted cents for the given funding."""
        raise NotImplementedError

    async def verify_waterfall_preview(self, settlement_id: str) -> dict[str, Any]:
        """INV-15: Compare UI waterfall preview to API waterfall result."""
        raise NotImplementedError
