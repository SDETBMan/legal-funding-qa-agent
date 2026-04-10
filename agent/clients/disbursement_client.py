from __future__ import annotations

import httpx
import structlog

class DisbursementClient:
    """
    Typed httpx wrapper for settlement disbursement endpoints; every call is logged (§6.1).

    Waterfall and remainder rules follow INV-07, INV-09, and INV-11.
    """

    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        self._client = client if client is not None else httpx.Client(base_url=base_url)
        self.log = structlog.get_logger(__name__)

    def preview_waterfall(self, settlement_id: str) -> httpx.Response:
        """INV-07, INV-09, INV-11: Ordered disbursement preview in integer cents."""
        raise NotImplementedError

    def disburse(self, settlement_id: str, body: dict) -> httpx.Response:
        """INV-03, INV-07, INV-09: Execute disbursement after attorney acknowledgment."""
        raise NotImplementedError
