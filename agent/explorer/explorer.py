from __future__ import annotations

from typing import Any

from agent.clients.disbursement_client import DisbursementClient
from agent.clients.funding_client import FundingClient

class HappyPathExplorer:
    """
    Happy-path API walkthrough: apply → approve → disburse → payoff (§3).

    Exercises API-layer invariants INV-01 through INV-12 across the nominal lifecycle.
    """

    def __init__(
        self,
        funding: FundingClient,
        disbursement: DisbursementClient,
    ) -> None:
        self._funding = funding
        self._disbursement = disbursement

    def run(self) -> dict[str, Any]:
        """Execute the scripted happy path and return step summaries for the report."""
        raise NotImplementedError
