from __future__ import annotations

import os
from typing import Any

import httpx
import structlog

class FundingClient:
    """
    Typed httpx wrapper for funding endpoints; every call is logged (§6.1).

    Response bodies must represent money as integer cents per INV-11.
    """

    def __init__(self, client: httpx.Client | None = None) -> None:
        self.log = structlog.get_logger(__name__)
        if client is not None:
            self._client = client
        else:
            base_url = os.environ["MOVEDOCS_API_BASE"]
            self._client = httpx.Client(base_url=base_url)

    def _response_body_for_log(self, response: httpx.Response, *, endpoint: str) -> Any:
        try:
            return response.json()
        except ValueError:
            text = response.text
            max_len = 16_384
            if len(text) > max_len:
                text = f"{text[:max_len]}...<truncated>"
            self.log.warning(
                "api_resp_body_not_json",
                endpoint=endpoint,
                status_code=response.status_code,
                content_type=response.headers.get("content-type"),
                body_preview=text,
            )
            return {"_unparsed_body": text}

    def apply(self, case_id: str, amount_cents: int) -> httpx.Response:
        """INV-01, INV-05, INV-11: Submit application; amount is whole cents."""
        endpoint = "POST /funding/applications"
        self.log.info(
            "api_call",
            endpoint=endpoint,
            case_id=case_id,
            amount_cents=amount_cents,
        )
        response = self._client.post(
            "/funding/applications",
            json={"case_id": case_id, "amount_cents": amount_cents},
        )
        self.log.info(
            "api_resp",
            endpoint=endpoint,
            status=response.status_code,
            body=self._response_body_for_log(response, endpoint=endpoint),
        )
        return response

    def approve(self, application_id: str) -> httpx.Response:
        """INV-02, INV-05, INV-06: Approve funding subject to case status and caps."""
        endpoint = f"POST /funding/{application_id}/approve"
        self.log.info(
            "api_call",
            endpoint=endpoint,
            application_id=application_id,
        )
        response = self._client.post(f"/funding/{application_id}/approve")
        self.log.info(
            "api_resp",
            endpoint=endpoint,
            status=response.status_code,
            body=self._response_body_for_log(response, endpoint=endpoint),
        )
        return response

    def cancel(self, application_id: str) -> httpx.Response:
        """INV-10: Cancel application and release reserved case capacity."""
        endpoint = f"POST /funding/{application_id}/cancel"
        self.log.info(
            "api_call",
            endpoint=endpoint,
            application_id=application_id,
        )
        response = self._client.post(f"/funding/{application_id}/cancel")
        self.log.info(
            "api_resp",
            endpoint=endpoint,
            status=response.status_code,
            body=self._response_body_for_log(response, endpoint=endpoint),
        )
        return response

    def get_payoff(self, funding_id: str) -> httpx.Response:
        """INV-04, INV-11, INV-12: Fetch payoff; expect integer cents and correct day basis."""
        endpoint = f"GET /funding/{funding_id}/payoff"
        self.log.info(
            "api_call",
            endpoint=endpoint,
            funding_id=funding_id,
        )
        response = self._client.get(f"/funding/{funding_id}/payoff")
        self.log.info(
            "api_resp",
            endpoint=endpoint,
            status=response.status_code,
            body=self._response_body_for_log(response, endpoint=endpoint),
        )
        return response
