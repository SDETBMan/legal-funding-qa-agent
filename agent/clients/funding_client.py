from __future__ import annotations

import os
from datetime import date
from typing import Any

import httpx
import structlog

def _safe_json(r: httpx.Response) -> dict:
    """
    Parse JSON body for structured logging. Never raises — parse failures become a dict.

    On success, returns the parsed object if it is a ``dict``; otherwise wraps non-dict
    JSON (e.g. list) as ``{"_json": ...}`` so the return type is always ``dict``.
    """
    try:
        data = r.json()
    except ValueError as e:
        return {"parse_error": str(e)}
    if isinstance(data, dict):
        return data
    return {"_json": data}

class FundingClient:
    """
    Typed httpx wrapper for MoveDocs funding, cases, liens, and settlement endpoints.

    Every call is logged before send and after receive (§6.1). Money in bodies must
    be integer cents per INV-11.
    """

    def __init__(self, client: httpx.Client | None = None) -> None:
        self.log = structlog.get_logger(__name__)
        if client is not None:
            self._client = client
        else:
            base_url = os.environ["MOVEDOCS_API_BASE"]
            self._client = httpx.Client(base_url=base_url)

    def _log_call(
        self,
        *,
        endpoint: str,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> None:
        self.log.info(
            "api_call",
            endpoint=endpoint,
            method=method,
            path=path,
            params=params,
            json_body=json_body,
        )

    def _log_response(self, *, endpoint: str, response: httpx.Response) -> None:
        self.log.info(
            "api_resp",
            endpoint=endpoint,
            status=response.status_code,
            url=str(response.request.url),
            headers=dict(response.headers),
            body=_safe_json(response),
        )

    def list_cases(self) -> httpx.Response:
        endpoint = "GET /cases"
        path = "/cases"
        self._log_call(endpoint=endpoint, method="GET", path=path, params=None, json_body=None)
        response = self._client.get(path)
        self._log_response(endpoint=endpoint, response=response)
        return response

    def get_case(self, case_id: str) -> httpx.Response:
        endpoint = f"GET /cases/{case_id}"
        path = f"/cases/{case_id}"
        self._log_call(
            endpoint=endpoint,
            method="GET",
            path=path,
            params=None,
            json_body=None,
        )
        response = self._client.get(path)
        self._log_response(endpoint=endpoint, response=response)
        return response

    def apply_for_funding(
        self,
        case_id: str,
        amount_cents: int,
        applicant_name: str,
    ) -> httpx.Response:
        endpoint = "POST /funding/apply"
        path = "/funding/apply"
        json_body = {
            "case_id": case_id,
            "amount_cents": amount_cents,
            "applicant_name": applicant_name,
        }
        self._log_call(
            endpoint=endpoint,
            method="POST",
            path=path,
            params=None,
            json_body=json_body,
        )
        response = self._client.post(path, json=json_body)
        self._log_response(endpoint=endpoint, response=response)
        return response

    def apply(self, case_id: str, amount_cents: int) -> httpx.Response:
        """§6.5 attack template: ``apply`` delegates to the wire API with a default applicant name."""
        applicant_name = os.environ.get("MOVEDOCS_ATTACK_APPLICANT_NAME", "QA adversary agent")
        return self.apply_for_funding(case_id, amount_cents, applicant_name)

    def cancel(self, application_id: str) -> httpx.Response:
        """§6.5 attack template: ``cancel`` aliases ``cancel_funding``."""
        return self.cancel_funding(application_id)

    def approve_funding(self, application_id: str) -> httpx.Response:
        endpoint = f"POST /funding/{application_id}/approve"
        path = f"/funding/{application_id}/approve"
        self._log_call(
            endpoint=endpoint,
            method="POST",
            path=path,
            params=None,
            json_body=None,
        )
        response = self._client.post(path)
        self._log_response(endpoint=endpoint, response=response)
        return response

    def disburse_funding(self, application_id: str, disbursement_date: date) -> httpx.Response:
        endpoint = f"POST /funding/{application_id}/disburse"
        path = f"/funding/{application_id}/disburse"
        json_body = {"disbursement_date": disbursement_date.isoformat()}
        self._log_call(
            endpoint=endpoint,
            method="POST",
            path=path,
            params=None,
            json_body=json_body,
        )
        response = self._client.post(path, json=json_body)
        self._log_response(endpoint=endpoint, response=response)
        return response

    def get_payoff(self, contract_id: str, payoff_date: date) -> httpx.Response:
        endpoint = f"GET /funding/{contract_id}/payoff"
        path = f"/funding/{contract_id}/payoff"
        params = {"payoff_date": payoff_date.isoformat()}
        self._log_call(
            endpoint=endpoint,
            method="GET",
            path=path,
            params=params,
            json_body=None,
        )
        response = self._client.get(path, params=params)
        self._log_response(endpoint=endpoint, response=response)
        return response

    def cancel_funding(self, application_id: str) -> httpx.Response:
        endpoint = f"POST /funding/{application_id}/cancel"
        path = f"/funding/{application_id}/cancel"
        self._log_call(
            endpoint=endpoint,
            method="POST",
            path=path,
            params=None,
            json_body=None,
        )
        response = self._client.post(path)
        self._log_response(endpoint=endpoint, response=response)
        return response

    def create_lien(
        self,
        case_id: str,
        lien_type: str,
        balance_cents: int,
        original_billed_cents: int,
        lienholder_name: str,
        priority_rank: int,
    ) -> httpx.Response:
        endpoint = "POST /liens"
        path = "/liens"
        json_body = {
            "case_id": case_id,
            "lien_type": lien_type,
            "balance_cents": balance_cents,
            "original_billed_cents": original_billed_cents,
            "lienholder_name": lienholder_name,
            "priority_rank": priority_rank,
        }
        self._log_call(
            endpoint=endpoint,
            method="POST",
            path=path,
            params=None,
            json_body=json_body,
        )
        response = self._client.post(path, json=json_body)
        self._log_response(endpoint=endpoint, response=response)
        return response

    def record_settlement(self, case_id: str, settlement_cents: int) -> httpx.Response:
        endpoint = f"POST /cases/{case_id}/settle"
        path = f"/cases/{case_id}/settle"
        json_body = {"settlement_cents": settlement_cents}
        self._log_call(
            endpoint=endpoint,
            method="POST",
            path=path,
            params=None,
            json_body=json_body,
        )
        response = self._client.post(path, json=json_body)
        self._log_response(endpoint=endpoint, response=response)
        return response
