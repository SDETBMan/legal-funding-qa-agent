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

WATERFALL_SETTLEMENT_CENTS = 2_000_000
WATERFALL_ESTIMATED_CENTS = 10_000_000

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

def attack_waterfall_priority(c: FundingClient) -> AttackResult:
    """
    INV-07: Settlement waterfall order: Medicare/Medicaid super-priority → medical liens by priority_rank → funding payoff → attorney fees → plaintiff remainder.

    Invariant rule: "Settlement waterfall order: Medicare/Medicaid super-priority → medical liens by priority_rank → funding payoff → attorney fees → plaintiff remainder"
    Blast radius: "Legal liability to lienholders"
    """
    case_id: str | None = None
    try:
        cr = c.create_case(
            plaintiff_name="Waterfall Attack Plaintiff",
            attorney_name="Waterfall Attack Attorney",
            estimated_settlement_cents=WATERFALL_ESTIMATED_CENTS,
            jurisdiction="IL",
        )
        case_body = cr.json()
        if cr.status_code != 201:
            return AttackResult(
                rule="INV-07",
                status="INDETERMINATE",
                evidence={"status_code": cr.status_code, "body": case_body},
                reasoning="POST /cases did not return 201; cannot build waterfall scenario.",
            )
        case_id = str(case_body["case_id"])

        la = c.create_lien(
            case_id=case_id,
            lien_type="MEDICAL",
            priority_rank=1,
            balance_cents=500_000,
            original_billed_cents=500_000,
            lienholder_name="City Hospital",
        )
        if la.status_code not in (200, 201):
            return AttackResult(
                rule="INV-07",
                status="INDETERMINATE",
                evidence={"status_code": la.status_code, "body": la.json()},
                reasoning="Failed to create MEDICAL lien A for INV-07 scenario.",
            )

        lb = c.create_lien(
            case_id=case_id,
            lien_type="MEDICARE",
            priority_rank=2,
            balance_cents=300_000,
            original_billed_cents=300_000,
            lienholder_name="CMS",
        )
        if lb.status_code not in (200, 201):
            return AttackResult(
                rule="INV-07",
                status="INDETERMINATE",
                evidence={"status_code": lb.status_code, "body": lb.json()},
                reasoning="Failed to create MEDICARE lien B for INV-07 scenario.",
            )

        sr = c.record_settlement(case_id, WATERFALL_SETTLEMENT_CENTS)
        settle_body = sr.json()
        if sr.status_code not in (200, 201):
            return AttackResult(
                rule="INV-07",
                status="INDETERMINATE",
                evidence={"status_code": sr.status_code, "body": settle_body},
                reasoning="POST /cases/{case_id}/settle did not succeed; cannot read waterfall.",
            )

        waterfall = settle_body.get("waterfall")
        if not isinstance(waterfall, list) or len(waterfall) < 2:
            return AttackResult(
                rule="INV-07",
                status="INDETERMINATE",
                evidence=settle_body if isinstance(settle_body, dict) else {"body": settle_body},
                reasoning="Settlement response missing waterfall array with at least two lines.",
            )

        w0 = waterfall[0]
        w1 = waterfall[1]
        if not isinstance(w0, dict) or not isinstance(w1, dict):
            return AttackResult(
                rule="INV-07",
                status="INDETERMINATE",
                evidence=settle_body,
                reasoning="Waterfall entries are not objects with lien_type.",
            )

        t0 = w0.get("lien_type")
        t1 = w1.get("lien_type")

        if t0 == "MEDICAL" and t1 == "MEDICARE":
            return AttackResult(
                rule="INV-07",
                status="BREACHED",
                evidence={
                    "case_id": case_id,
                    "waterfall_first_two": [w0, w1],
                    "settlement_body": settle_body,
                },
                reasoning=(
                    "Medicare was paid second despite super-priority: waterfall[0] is MEDICAL "
                    "and waterfall[1] is MEDICARE."
                ),
            )
        if t0 == "MEDICARE":
            return AttackResult(
                rule="INV-07",
                status="HELD",
                evidence={
                    "case_id": case_id,
                    "waterfall_first_two": [w0, w1],
                    "settlement_body": settle_body,
                },
                reasoning="Medicare super-priority correctly enforced (Medicare before medical in waterfall).",
            )
        return AttackResult(
            rule="INV-07",
            status="INDETERMINATE",
            evidence={
                "case_id": case_id,
                "waterfall_first_two": [w0, w1],
                "settlement_body": settle_body,
            },
            reasoning=f"First two waterfall lien_types are {t0!r} then {t1!r}; expected MEDICAL+Medicare breach pattern or MEDICARE first for HELD.",
        )
    except Exception as exc:
        return AttackResult(
            rule="INV-07",
            status="INDETERMINATE",
            evidence={"exception": repr(exc), "case_id": case_id},
            reasoning="INV-07 waterfall scenario failed before a verdict could be formed.",
        )
    finally:
        if case_id is not None:
            log.info("waterfall_attack_case", case_id=case_id, rule="INV-07")

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
    "waterfall_priority": attack_waterfall_priority,  # INV-07: Medicare super-priority in settlement waterfall
}
