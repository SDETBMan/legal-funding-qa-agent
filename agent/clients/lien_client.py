from __future__ import annotations

import httpx
import structlog

class LienClient:
    """
    Typed httpx wrapper for lien management endpoints; every call is logged (§6.1).

    Lien balances and priorities must respect INV-07 and INV-08.
    """

    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        self._client = client if client is not None else httpx.Client(base_url=base_url)
        self.log = structlog.get_logger(__name__)

    def list_liens(self, case_id: str) -> httpx.Response:
        """INV-07: Retrieve liens including Medicare/Medicaid and priority_rank ordering."""
        raise NotImplementedError

    def create_lien(self, case_id: str, body: dict) -> httpx.Response:
        """INV-08, INV-11: Create lien; balance must not exceed original billed amount."""
        raise NotImplementedError
