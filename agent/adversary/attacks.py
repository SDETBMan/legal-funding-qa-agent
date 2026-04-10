from __future__ import annotations

import os
from collections.abc import Callable
from datetime import date
from typing import Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field

from agent.clients.disbursement_client import DisbursementClient
from agent.clients.funding_client import FundingClient
from agent.clients.lien_client import LienClient

log = structlog.get_logger(__name__)

class AttackResult(BaseModel):
    """
    Observation payload for the Judge; attacks collect evidence per §6.5.

    Each attack function must declare its INV-XX target in its docstring first line.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule: str
    status: Literal["HELD", "BREACHED", "INDETERMINATE"]
    evidence: dict = Field(default_factory=dict)
    reasoning: str = ""

def attack_duplicate_funding(c: FundingClient) -> AttackResult:
    """
    INV-01: A second active funding application on the same case
    must be rejected or routed to manual review.
    """
    created_ids: list[str] = []
    try:
        SEED_CASE_ID = os.environ["MOVEDOCS_SEED_CASE_ID"]
        app_1 = c.apply(case_id=SEED_CASE_ID, amount_cents=500_000)
        created_ids.append(app_1.json()["application_id"])
        app_2 = c.apply(case_id=SEED_CASE_ID, amount_cents=300_000)
        body_2 = app_2.json()

        if app_2.status_code == 201:
            created_ids.append(body_2["application_id"])
            return AttackResult(
                rule="INV-01", status="BREACHED",
                evidence={"app_1": app_1.json(), "app_2": body_2},
                reasoning="Platform accepted a second active funding on the same case.",
            )
        elif app_2.status_code in (409, 422):
            return AttackResult(rule="INV-01", status="HELD",
                                evidence=body_2, reasoning="Duplicate correctly rejected.")
        else:
            return AttackResult(rule="INV-01", status="INDETERMINATE",
                                evidence=body_2, reasoning="Unexpected status — Judge to evaluate.")
    finally:
        for aid in created_ids:
            try: c.cancel(aid)
            except Exception: log.warning("cleanup_failed", application_id=aid)

def attack_closed_case_funding(c: FundingClient) -> AttackResult:
    """
    INV-02: Funding cannot be approved if case status is settled, dismissed, or closed.
    """
    created_ids: list[str] = []
    try:
        CLOSED_CASE_ID = os.environ["MOVEDOCS_CLOSED_CASE_ID"]
        app_1 = c.apply(case_id=CLOSED_CASE_ID, amount_cents=500_000)
        created_ids.append(app_1.json()["application_id"])
        appr = c.approve_funding(application_id=created_ids[0])
        body_2 = appr.json()

        if appr.status_code in (200, 201):
            return AttackResult(
                rule="INV-02",
                status="BREACHED",
                evidence={"app_1": app_1.json(), "app_2": body_2},
                reasoning="Platform approved funding for a case in settled, dismissed, or closed status.",
            )
        elif appr.status_code in (409, 422):
            return AttackResult(
                rule="INV-02",
                status="HELD",
                evidence=body_2,
                reasoning="Approval correctly rejected for terminal case.",
            )
        else:
            return AttackResult(
                rule="INV-02",
                status="INDETERMINATE",
                evidence=body_2,
                reasoning="Unexpected status — Judge to evaluate.",
            )
    finally:
        for aid in created_ids:
            try:
                c.cancel(aid)
            except Exception:
                log.warning("cleanup_failed", application_id=aid)

def attack_disburse_without_attorney_ack(c: FundingClient) -> AttackResult:
    """
    INV-03: Attorney acknowledgment must exist and be dated before funds disburse.

    Invariant rule: "Attorney acknowledgment must exist and be dated before funds disburse"
    Blast radius: "Legal liability / clawback"
    """
    created_ids: list[str] = []
    try:
        CASE_ID = os.environ["MOVEDOCS_SEED_CASE_ID"]
        DISBURSE_DAY = date.fromisoformat(os.environ["MOVEDOCS_DISBURSEMENT_DATE"])
        app_1 = c.apply(case_id=CASE_ID, amount_cents=500_000)
        created_ids.append(app_1.json()["application_id"])
        c.approve_funding(application_id=created_ids[0])
        disb = c.disburse_funding(application_id=created_ids[0], disbursement_date=DISBURSE_DAY)
        body_d = disb.json()

        if disb.status_code in (200, 201):
            return AttackResult(
                rule="INV-03", status="BREACHED",
                evidence={"app_1": app_1.json(), "disburse": body_d},
                reasoning="Platform disbursed without a recorded attorney acknowledgment dated before disbursement.",
            )
        elif disb.status_code == 422:
            return AttackResult(rule="INV-03", status="HELD",
                                evidence=body_d, reasoning="Disbursement correctly blocked without attorney acknowledgment.")
        else:
            return AttackResult(rule="INV-03", status="INDETERMINATE",
                                evidence=body_d, reasoning="Unexpected status — Judge to evaluate.")
    finally:
        for aid in created_ids:
            try: c.cancel(aid)
            except Exception: log.warning("cleanup_failed", application_id=aid)

def attack_payoff_component_mismatch(c: FundingClient) -> AttackResult:
    """INV-04: Payoff equals principal + accrued interest + fees from disbursement_date accrual."""
    raise NotImplementedError

def attack_exceeds_case_max_exposure(c: FundingClient) -> AttackResult:
    """INV-05: Approved funding must be <= case_max_exposure at time of approval."""
    raise NotImplementedError

def attack_usury_rate_cap(c: FundingClient) -> AttackResult:
    """INV-06: Jurisdiction rate cap enforced — interest must not exceed applicable usury limit."""
    raise NotImplementedError

def attack_waterfall_order_violation(c: DisbursementClient) -> AttackResult:
    """INV-07: Settlement waterfall order: Medicare/Medicaid → medical by rank → funding → fees → remainder."""
    raise NotImplementedError

def attack_lien_balance_exceeds_billed(c: LienClient) -> AttackResult:
    """INV-08: Medical lien balance cannot exceed original_billed_amount."""
    raise NotImplementedError

def attack_negative_plaintiff_remainder(c: DisbursementClient) -> AttackResult:
    """INV-09: Plaintiff remainder after waterfall must be >= 0; no disburse if obligations exceed settlement."""
    raise NotImplementedError

def attack_cancelled_application_capacity_leak(c: FundingClient) -> AttackResult:
    """INV-10: Cancelled or expired applications release reserved case capacity immediately."""
    raise NotImplementedError

def attack_float_money_in_api_response(c: FundingClient) -> AttackResult:
    """INV-11: All money fields are integer cents — never floats or ambiguous strings."""
    raise NotImplementedError

def attack_float_payoff(c: FundingClient) -> AttackResult:
    """
    INV-11: All money fields are integer cents — never floats, never strings with >2dp.

    Observes GET payoff: if ``total_cents`` is a JSON float, the API violates INV-11.
    """
    contract_id = os.environ["MOVEDOCS_CONTRACT_ID"]
    payoff_date = date.fromisoformat(os.environ["MOVEDOCS_PAYOFF_DATE"])
    r = c.get_payoff(contract_id, payoff_date)
    body = r.json()
    evidence: dict = {"status_code": r.status_code, "body": body}

    if r.status_code != 200:
        return AttackResult(
            rule="INV-11",
            status="INDETERMINATE",
            evidence=evidence,
            reasoning="Payoff request did not succeed; cannot evaluate money field types.",
        )

    total = body.get("total_cents")
    if isinstance(total, float):
        return AttackResult(
            rule="INV-11",
            status="BREACHED",
            evidence=evidence,
            reasoning="API returned total_cents as float; integer cents required per INV-11.",
        )
    if type(total) is int:
        return AttackResult(
            rule="INV-11",
            status="HELD",
            evidence=evidence,
            reasoning="total_cents is integer-typed in payoff response.",
        )
    return AttackResult(
        rule="INV-11",
        status="INDETERMINATE",
        evidence=evidence,
        reasoning="total_cents missing or unexpected type for INV-11 evaluation.",
    )

def attack_interest_from_application_date(c: FundingClient) -> AttackResult:
    """
    INV-04: Payoff = principal_cents + accrued_interest_cents + fees_cents; interest accrues from disbursement_date, not application_date.

    Invariant rule: "Payoff = principal_cents + accrued_interest_cents + fees_cents; interest accrues from disbursement_date, not application_date"
    Blast radius: "Direct $ — overcharge or undercharge plaintiff"
    """
    try:
        contract_id = os.environ.get("MOVEDOCS_CONTRACT_ID", "CONTRACT-SEED-001")
        payoff_day = date.today()
        r = c.get_payoff(contract_id, payoff_day)
        body = r.json()

        if r.status_code != 200:
            return AttackResult(
                rule="INV-04",
                status="INDETERMINATE",
                evidence={"status_code": r.status_code, "body": body},
                reasoning="Payoff GET did not return 200; cannot evaluate interest accrual basis.",
            )

        required = (
            "interest_start_date",
            "disbursement_date",
            "principal_cents",
            "rate_bps",
            "days_elapsed",
        )
        missing = [k for k in required if k not in body]
        if missing:
            return AttackResult(
                rule="INV-04",
                status="INDETERMINATE",
                evidence=body if isinstance(body, dict) else {"body": body},
                reasoning=f"Payoff response missing required field(s) for INV-04: {', '.join(missing)}.",
            )

        interest_start_date = body["interest_start_date"]
        disbursement_date = body["disbursement_date"]
        principal_cents = int(body["principal_cents"])
        rate_bps = int(body["rate_bps"])
        _ = int(body["days_elapsed"])

        d_start = date.fromisoformat(str(interest_start_date))
        d_disb = date.fromisoformat(str(disbursement_date))

        if d_start == d_disb:
            return AttackResult(
                rule="INV-04",
                status="HELD",
                evidence=body,
                reasoning="Interest correctly accrues from disbursement_date.",
            )

        correct_days = (payoff_day - d_disb).days
        wrong_days = (payoff_day - d_start).days
        overcharge_days = wrong_days - correct_days
        overcharge_cents = (principal_cents * rate_bps * overcharge_days) // (10_000 * 365)
        oc = overcharge_cents
        overcharge_dollars = f"${oc // 100}.{oc % 100:02d}"

        return AttackResult(
            rule="INV-04",
            status="BREACHED",
            evidence={
                "interest_start_date": interest_start_date,
                "disbursement_date": disbursement_date,
                "overcharge_days": overcharge_days,
                "overcharge_cents": overcharge_cents,
                "overcharge_dollars": overcharge_dollars,
            },
            reasoning=(
                f"Interest accrues from {interest_start_date} (application date) "
                f"instead of {disbursement_date} (disbursement date). "
                f"Plaintiff overcharged by {overcharge_days} days = "
                f"{overcharge_cents} cents ({overcharge_dollars})."
            ),
        )
    except Exception as exc:
        return AttackResult(
            rule="INV-04",
            status="INDETERMINATE",
            evidence={"exception": repr(exc)},
            reasoning="INV-04 payoff inspection failed before a verdict could be formed.",
        )

def attack_interest_day_count_basis(c: FundingClient) -> AttackResult:
    """INV-12: Interest uses exact calendar day count from disbursement_date to payoff_date."""
    raise NotImplementedError

AttackFn = Callable[..., AttackResult]

ATTACKS: dict[str, Callable[[FundingClient], AttackResult]] = {
    "duplicate_funding": attack_duplicate_funding,
    "disburse_without_attorney_ack": attack_disburse_without_attorney_ack,  # INV-03: disburse without ack
    "float_payoff": attack_float_payoff,
    "interest_from_application_date": attack_interest_from_application_date,  # INV-04: interest from application date
}
