from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field

from agent.clients.funding_client import FundingClient

log = structlog.get_logger(__name__)

WATERFALL_SETTLEMENT_CENTS = 2_000_000
WATERFALL_ESTIMATED_CENTS = 10_000_000

_ROOT = Path(__file__).resolve().parent.parent.parent


class AttackResult(BaseModel):
    """
    Observation payload for the Judge; attacks collect evidence per S6.5.

    Each attack function must declare its INV-XX target in its docstring first line.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule: str
    status: Literal["HELD", "BREACHED", "INDETERMINATE"]
    evidence: dict = Field(default_factory=dict)
    reasoning: str = ""


# ---------------------------------------------------------------------------
# INV-01: No duplicate active funding
# ---------------------------------------------------------------------------

def attack_duplicate_funding(c: FundingClient) -> AttackResult:
    """
    INV-01: A second active funding application on the same case
    must be rejected or routed to manual review.
    """
    created_ids: list[str] = []
    try:
        SEED_CASE_ID = os.environ["FUNDING_SEED_CASE_ID"]
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
                                evidence=body_2, reasoning="Unexpected status -- Judge to evaluate.")
    finally:
        for aid in created_ids:
            try: c.cancel(aid)
            except Exception: log.warning("cleanup_failed", application_id=aid)


# ---------------------------------------------------------------------------
# INV-02: No funding on closed/settled/dismissed cases
# ---------------------------------------------------------------------------

def attack_closed_case_funding(c: FundingClient) -> AttackResult:
    """
    INV-02: Funding cannot be approved if case status is settled, dismissed, or closed.
    """
    created_ids: list[str] = []
    try:
        CLOSED_CASE_ID = os.environ["FUNDING_CLOSED_CASE_ID"]
        app_1 = c.apply(case_id=CLOSED_CASE_ID, amount_cents=500_000)
        app_body = app_1.json()

        # If the apply itself is rejected, INV-02 is held at the application stage
        if app_1.status_code in (409, 422):
            return AttackResult(
                rule="INV-02",
                status="HELD",
                evidence=app_body,
                reasoning="Application correctly rejected for non-active case status.",
            )

        if app_1.status_code != 201:
            return AttackResult(
                rule="INV-02",
                status="INDETERMINATE",
                evidence=app_body,
                reasoning=f"Unexpected apply status {app_1.status_code} -- Judge to evaluate.",
            )

        created_ids.append(app_body["application_id"])
        appr = c.approve_funding(application_id=created_ids[0])
        body_2 = appr.json()

        if appr.status_code in (200, 201):
            return AttackResult(
                rule="INV-02",
                status="BREACHED",
                evidence={"app_1": app_body, "app_2": body_2},
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
                reasoning="Unexpected status -- Judge to evaluate.",
            )
    finally:
        for aid in created_ids:
            try:
                c.cancel(aid)
            except Exception:
                log.warning("cleanup_failed", application_id=aid)


# ---------------------------------------------------------------------------
# INV-03: Attorney acknowledgment before disbursement
# ---------------------------------------------------------------------------

def attack_disburse_without_attorney_ack(c: FundingClient) -> AttackResult:
    """
    INV-03: Attorney acknowledgment must exist and be dated before funds disburse.
    """
    created_ids: list[str] = []
    try:
        CASE_ID = os.environ["FUNDING_SEED_CASE_ID"]
        DISBURSE_DAY = date.fromisoformat(os.environ["FUNDING_DISBURSEMENT_DATE"])
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
                                evidence=body_d, reasoning="Unexpected status -- Judge to evaluate.")
    finally:
        for aid in created_ids:
            try: c.cancel(aid)
            except Exception: log.warning("cleanup_failed", application_id=aid)


# ---------------------------------------------------------------------------
# INV-04: Payoff component correctness (interest from disbursement_date)
# ---------------------------------------------------------------------------

def attack_interest_from_application_date(c: FundingClient) -> AttackResult:
    """
    INV-04: Payoff = principal_cents + accrued_interest_cents + fees_cents; interest accrues from disbursement_date, not application_date.
    """
    try:
        contract_id = os.environ.get("FUNDING_CONTRACT_ID", "CONTRACT-SEED-001")
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


# ---------------------------------------------------------------------------
# INV-05: Approved funding <= case_max_exposure
# ---------------------------------------------------------------------------

def attack_exceeds_case_max_exposure(c: FundingClient) -> AttackResult:
    """INV-05: Approved funding must be <= case_max_exposure at time of approval."""
    case_id: str | None = None
    created_ids: list[str] = []
    try:
        # Create a case with a small estimated settlement so max_exposure is low
        cr = c.create_case(
            plaintiff_name="MaxExposure Attack Plaintiff",
            attorney_name="MaxExposure Attack Attorney",
            estimated_settlement_cents=100_000,  # $1,000 -> max_exposure = $200 (20%)
            jurisdiction="IL",
        )
        case_body = cr.json()
        if cr.status_code != 201:
            return AttackResult(
                rule="INV-05", status="INDETERMINATE",
                evidence={"status_code": cr.status_code, "body": case_body},
                reasoning="POST /cases did not return 201.",
            )
        case_id = str(case_body["case_id"])
        max_exposure = case_body.get("case_max_exposure_cents", 0)

        # Apply for an amount that exceeds max_exposure
        over_amount = max_exposure + 50_000  # $500 over the cap
        app_r = c.apply(case_id=case_id, amount_cents=over_amount)
        app_body = app_r.json()

        if app_r.status_code == 201:
            created_ids.append(app_body["application_id"])
            # Approve it -- the approve endpoint has BUG-04 (no re-check)
            appr = c.approve_funding(application_id=app_body["application_id"])
            appr_body = appr.json()
            if appr.status_code in (200, 201):
                return AttackResult(
                    rule="INV-05", status="BREACHED",
                    evidence={
                        "case_id": case_id,
                        "case_max_exposure_cents": max_exposure,
                        "approved_amount_cents": over_amount,
                        "approve_response": appr_body,
                    },
                    reasoning=(
                        f"Funding of {over_amount} cents approved despite case_max_exposure "
                        f"of {max_exposure} cents."
                    ),
                )
            return AttackResult(
                rule="INV-05", status="HELD",
                evidence={"approve_response": appr_body},
                reasoning="Approval correctly rejected for over-exposure.",
            )
        elif app_r.status_code in (409, 422):
            return AttackResult(
                rule="INV-05", status="HELD",
                evidence=app_body,
                reasoning="Application correctly rejected for exceeding case_max_exposure.",
            )
        else:
            return AttackResult(
                rule="INV-05", status="INDETERMINATE",
                evidence=app_body,
                reasoning=f"Unexpected status {app_r.status_code} on apply.",
            )
    except Exception as exc:
        return AttackResult(
            rule="INV-05", status="INDETERMINATE",
            evidence={"exception": repr(exc), "case_id": case_id},
            reasoning="INV-05 max exposure attack failed before a verdict could be formed.",
        )
    finally:
        for aid in created_ids:
            try: c.cancel(aid)
            except Exception: log.warning("cleanup_failed", application_id=aid)


# ---------------------------------------------------------------------------
# INV-06: Jurisdiction usury rate cap
# ---------------------------------------------------------------------------

def attack_usury_rate_cap(c: FundingClient) -> AttackResult:
    """INV-06: Jurisdiction rate cap enforced -- interest must not exceed applicable usury limit."""
    try:
        contract_id = os.environ.get("FUNDING_CONTRACT_ID", "CONTRACT-SEED-001")

        # Read the contract to get rate_bps and jurisdiction
        cr = c.get_contract(contract_id)
        if cr.status_code != 200:
            return AttackResult(
                rule="INV-06", status="INDETERMINATE",
                evidence={"status_code": cr.status_code},
                reasoning=f"GET /contracts/{contract_id} returned {cr.status_code}.",
            )
        contract = cr.json()
        rate_bps = contract.get("rate_bps")
        jurisdiction = contract.get("jurisdiction")

        if rate_bps is None or jurisdiction is None:
            return AttackResult(
                rule="INV-06", status="INDETERMINATE",
                evidence=contract,
                reasoning="Contract missing rate_bps or jurisdiction field.",
            )

        # Load jurisdiction rate caps
        caps_path = _ROOT / "config" / "rate_caps.json"
        if not caps_path.exists():
            return AttackResult(
                rule="INV-06", status="INDETERMINATE",
                evidence={"caps_path": str(caps_path)},
                reasoning="config/rate_caps.json not found; cannot evaluate usury cap.",
            )
        caps = json.loads(caps_path.read_text(encoding="utf-8"))
        cap_bps = caps.get(jurisdiction)

        if cap_bps is None:
            return AttackResult(
                rule="INV-06", status="INDETERMINATE",
                evidence={"jurisdiction": jurisdiction, "available_jurisdictions": list(caps.keys())},
                reasoning=f"No usury cap configured for jurisdiction {jurisdiction!r}.",
            )

        if int(rate_bps) > int(cap_bps):
            return AttackResult(
                rule="INV-06", status="BREACHED",
                evidence={
                    "contract_id": contract_id,
                    "jurisdiction": jurisdiction,
                    "contract_rate_bps": rate_bps,
                    "jurisdiction_cap_bps": cap_bps,
                    "excess_bps": int(rate_bps) - int(cap_bps),
                },
                reasoning=(
                    f"Contract rate {rate_bps} bps exceeds {jurisdiction} usury cap "
                    f"of {cap_bps} bps by {int(rate_bps) - int(cap_bps)} bps."
                ),
            )
        return AttackResult(
            rule="INV-06", status="HELD",
            evidence={
                "contract_id": contract_id,
                "jurisdiction": jurisdiction,
                "contract_rate_bps": rate_bps,
                "jurisdiction_cap_bps": cap_bps,
            },
            reasoning=f"Contract rate {rate_bps} bps within {jurisdiction} cap of {cap_bps} bps.",
        )
    except Exception as exc:
        return AttackResult(
            rule="INV-06", status="INDETERMINATE",
            evidence={"exception": repr(exc)},
            reasoning="INV-06 usury rate cap check failed before a verdict could be formed.",
        )


# ---------------------------------------------------------------------------
# INV-07: Settlement waterfall order (Medicare super-priority)
# ---------------------------------------------------------------------------

def attack_waterfall_priority(c: FundingClient) -> AttackResult:
    """
    INV-07: Settlement waterfall order: Medicare/Medicaid super-priority -> medical liens by priority_rank -> funding payoff -> attorney fees -> plaintiff remainder.
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


# ---------------------------------------------------------------------------
# INV-08: Lien balance cannot exceed original_billed
# ---------------------------------------------------------------------------

def attack_lien_balance_exceeds_billed(c: FundingClient) -> AttackResult:
    """INV-08: Medical lien balance cannot exceed original_billed_amount."""
    case_id: str | None = None
    try:
        cr = c.create_case(
            plaintiff_name="Lien Overcharge Plaintiff",
            attorney_name="Lien Overcharge Attorney",
            estimated_settlement_cents=5_000_000,
            jurisdiction="IL",
        )
        case_body = cr.json()
        if cr.status_code != 201:
            return AttackResult(
                rule="INV-08", status="INDETERMINATE",
                evidence={"status_code": cr.status_code, "body": case_body},
                reasoning="POST /cases did not return 201.",
            )
        case_id = str(case_body["case_id"])

        # Attempt to create a lien where balance > original_billed
        original_billed = 100_000  # $1,000
        inflated_balance = 150_000  # $1,500 — exceeds original_billed by $500
        lr = c.create_lien(
            case_id=case_id,
            lien_type="MEDICAL",
            priority_rank=1,
            balance_cents=inflated_balance,
            original_billed_cents=original_billed,
            lienholder_name="Overcharge Hospital",
        )
        lien_body = lr.json()

        if lr.status_code in (200, 201):
            return AttackResult(
                rule="INV-08", status="BREACHED",
                evidence={
                    "case_id": case_id,
                    "lien": lien_body,
                    "balance_cents": inflated_balance,
                    "original_billed_cents": original_billed,
                    "excess_cents": inflated_balance - original_billed,
                },
                reasoning=(
                    f"Lien accepted with balance_cents ({inflated_balance}) exceeding "
                    f"original_billed_cents ({original_billed}) by "
                    f"{inflated_balance - original_billed} cents."
                ),
            )
        elif lr.status_code in (400, 422):
            return AttackResult(
                rule="INV-08", status="HELD",
                evidence=lien_body,
                reasoning="Lien correctly rejected: balance exceeds original billed amount.",
            )
        else:
            return AttackResult(
                rule="INV-08", status="INDETERMINATE",
                evidence=lien_body,
                reasoning=f"Unexpected status {lr.status_code} on lien creation.",
            )
    except Exception as exc:
        return AttackResult(
            rule="INV-08", status="INDETERMINATE",
            evidence={"exception": repr(exc), "case_id": case_id},
            reasoning="INV-08 lien balance attack failed before a verdict could be formed.",
        )


# ---------------------------------------------------------------------------
# INV-09: Plaintiff remainder >= 0
# ---------------------------------------------------------------------------

def attack_negative_plaintiff_remainder(c: FundingClient) -> AttackResult:
    """INV-09: Plaintiff remainder after waterfall must be >= 0; no disburse if obligations exceed settlement."""
    case_id: str | None = None
    try:
        # Create a case with modest estimated settlement
        cr = c.create_case(
            plaintiff_name="Negative Remainder Plaintiff",
            attorney_name="Negative Remainder Attorney",
            estimated_settlement_cents=5_000_000,
            jurisdiction="IL",
        )
        case_body = cr.json()
        if cr.status_code != 201:
            return AttackResult(
                rule="INV-09", status="INDETERMINATE",
                evidence={"status_code": cr.status_code, "body": case_body},
                reasoning="POST /cases did not return 201.",
            )
        case_id = str(case_body["case_id"])

        # Stack liens that exceed the settlement amount
        for i, (amount, name) in enumerate([
            (400_000, "Hospital A"),
            (400_000, "Hospital B"),
            (400_000, "Hospital C"),
        ], start=1):
            lr = c.create_lien(
                case_id=case_id,
                lien_type="MEDICAL",
                priority_rank=i,
                balance_cents=amount,
                original_billed_cents=amount,
                lienholder_name=name,
            )
            if lr.status_code not in (200, 201):
                return AttackResult(
                    rule="INV-09", status="INDETERMINATE",
                    evidence={"status_code": lr.status_code, "body": lr.json()},
                    reasoning=f"Failed to create lien {i} for INV-09 scenario.",
                )

        # Settle for less than total liens (1.2M liens vs 500K settlement)
        sr = c.record_settlement(case_id, 500_000)
        settle_body = sr.json()

        if sr.status_code not in (200, 201):
            return AttackResult(
                rule="INV-09", status="INDETERMINATE",
                evidence={"status_code": sr.status_code, "body": settle_body},
                reasoning="Settlement request failed.",
            )

        remainder = settle_body.get("plaintiff_remainder_cents")
        remainder_valid = settle_body.get("plaintiff_remainder_valid")

        if remainder is not None and int(remainder) < 0:
            return AttackResult(
                rule="INV-09", status="BREACHED",
                evidence={
                    "case_id": case_id,
                    "settlement_cents": 500_000,
                    "plaintiff_remainder_cents": remainder,
                    "plaintiff_remainder_valid": remainder_valid,
                    "waterfall": settle_body.get("waterfall", []),
                },
                reasoning=(
                    f"Settlement produced negative plaintiff remainder of {remainder} cents. "
                    "Platform should reject settlement when obligations exceed amount."
                ),
            )
        return AttackResult(
            rule="INV-09", status="HELD",
            evidence=settle_body,
            reasoning=f"Plaintiff remainder is {remainder} cents (non-negative).",
        )
    except Exception as exc:
        return AttackResult(
            rule="INV-09", status="INDETERMINATE",
            evidence={"exception": repr(exc), "case_id": case_id},
            reasoning="INV-09 negative remainder attack failed before a verdict could be formed.",
        )


# ---------------------------------------------------------------------------
# INV-10: Cancelled apps release reserved capacity
# ---------------------------------------------------------------------------

def attack_cancelled_application_capacity_leak(c: FundingClient) -> AttackResult:
    """INV-10: Cancelled or expired applications release reserved case capacity immediately."""
    case_id: str | None = None
    created_ids: list[str] = []
    try:
        cr = c.create_case(
            plaintiff_name="Capacity Leak Plaintiff",
            attorney_name="Capacity Leak Attorney",
            estimated_settlement_cents=500_000,  # $5,000 -> max_exposure = $1,000
            jurisdiction="IL",
        )
        case_body = cr.json()
        if cr.status_code != 201:
            return AttackResult(
                rule="INV-10", status="INDETERMINATE",
                evidence={"status_code": cr.status_code, "body": case_body},
                reasoning="POST /cases did not return 201.",
            )
        case_id = str(case_body["case_id"])
        max_exposure = case_body.get("case_max_exposure_cents", 0)

        # Apply for an amount within the cap
        amount = min(max_exposure, 50_000) if max_exposure > 0 else 50_000
        app_r = c.apply(case_id=case_id, amount_cents=amount)
        if app_r.status_code != 201:
            return AttackResult(
                rule="INV-10", status="INDETERMINATE",
                evidence={"status_code": app_r.status_code, "body": app_r.json()},
                reasoning="Initial application failed.",
            )
        app_id = app_r.json()["application_id"]
        created_ids.append(app_id)

        # Cancel the application
        cancel_r = c.cancel(app_id)
        if cancel_r.status_code not in (200, 201):
            return AttackResult(
                rule="INV-10", status="INDETERMINATE",
                evidence={"status_code": cancel_r.status_code, "body": cancel_r.json()},
                reasoning="Cancel request failed.",
            )

        # Check capacity -- should be fully available again
        cap_r = c.get_case_capacity(case_id)
        if cap_r.status_code != 200:
            return AttackResult(
                rule="INV-10", status="INDETERMINATE",
                evidence={"status_code": cap_r.status_code},
                reasoning="GET /cases/{id}/capacity failed.",
            )
        cap_body = cap_r.json()
        reserved = cap_body.get("reserved_cents", 0)

        if reserved > 0:
            return AttackResult(
                rule="INV-10", status="BREACHED",
                evidence={
                    "case_id": case_id,
                    "cancelled_app_id": app_id,
                    "reserved_after_cancel_cents": reserved,
                    "capacity": cap_body,
                },
                reasoning=(
                    f"After cancelling application {app_id}, reserved capacity is still "
                    f"{reserved} cents. Should be 0."
                ),
            )

        # Try re-applying for the full amount to confirm capacity was released
        reapp_r = c.apply(case_id=case_id, amount_cents=amount)
        reapp_body = reapp_r.json()
        if reapp_r.status_code == 201:
            created_ids.append(reapp_body["application_id"])
            return AttackResult(
                rule="INV-10", status="HELD",
                evidence={"capacity": cap_body, "reapply": reapp_body},
                reasoning="Capacity correctly released after cancel; re-application succeeded.",
            )
        return AttackResult(
            rule="INV-10", status="BREACHED",
            evidence={
                "case_id": case_id,
                "capacity": cap_body,
                "reapply_status": reapp_r.status_code,
                "reapply_body": reapp_body,
            },
            reasoning="Re-application blocked after cancel -- capacity not released.",
        )
    except Exception as exc:
        return AttackResult(
            rule="INV-10", status="INDETERMINATE",
            evidence={"exception": repr(exc), "case_id": case_id},
            reasoning="INV-10 capacity leak attack failed before a verdict could be formed.",
        )
    finally:
        for aid in created_ids:
            try: c.cancel(aid)
            except Exception: log.warning("cleanup_failed", application_id=aid)


# ---------------------------------------------------------------------------
# INV-11: All money fields are integer cents
# ---------------------------------------------------------------------------

def attack_float_payoff(c: FundingClient) -> AttackResult:
    """
    INV-11: All money fields are integer cents -- never floats, never strings with >2dp.

    Observes GET payoff: if ``total_cents`` is a JSON float, the API violates INV-11.
    """
    contract_id = os.environ["FUNDING_CONTRACT_ID"]
    payoff_date = date.fromisoformat(os.environ["FUNDING_PAYOFF_DATE"])
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


# ---------------------------------------------------------------------------
# INV-12: Interest uses exact calendar day count
# ---------------------------------------------------------------------------

def attack_interest_day_count_basis(c: FundingClient) -> AttackResult:
    """INV-12: Interest uses exact calendar day count from disbursement_date to payoff_date."""
    try:
        contract_id = os.environ.get("FUNDING_CONTRACT_ID", "CONTRACT-SEED-001")
        payoff_day = date.today()
        r = c.get_payoff(contract_id, payoff_day)
        body = r.json()

        if r.status_code != 200:
            return AttackResult(
                rule="INV-12", status="INDETERMINATE",
                evidence={"status_code": r.status_code, "body": body},
                reasoning="Payoff GET did not return 200.",
            )

        required = ("disbursement_date", "days_elapsed", "payoff_date")
        missing = [k for k in required if k not in body]
        if missing:
            return AttackResult(
                rule="INV-12", status="INDETERMINATE",
                evidence=body if isinstance(body, dict) else {"body": body},
                reasoning=f"Payoff response missing field(s): {', '.join(missing)}.",
            )

        api_days = int(body["days_elapsed"])
        disbursement_date = date.fromisoformat(str(body["disbursement_date"]))
        payoff_date_resp = date.fromisoformat(str(body["payoff_date"]))
        exact_days = (payoff_date_resp - disbursement_date).days

        if api_days == exact_days:
            return AttackResult(
                rule="INV-12", status="HELD",
                evidence={
                    "disbursement_date": str(disbursement_date),
                    "payoff_date": str(payoff_date_resp),
                    "api_days_elapsed": api_days,
                    "exact_calendar_days": exact_days,
                },
                reasoning=f"days_elapsed ({api_days}) matches exact calendar day count.",
            )

        delta = api_days - exact_days
        return AttackResult(
            rule="INV-12", status="BREACHED",
            evidence={
                "disbursement_date": str(disbursement_date),
                "payoff_date": str(payoff_date_resp),
                "api_days_elapsed": api_days,
                "exact_calendar_days": exact_days,
                "delta_days": delta,
            },
            reasoning=(
                f"days_elapsed ({api_days}) does not match exact calendar days "
                f"({exact_days}); delta = {delta} day(s)."
            ),
        )
    except Exception as exc:
        return AttackResult(
            rule="INV-12", status="INDETERMINATE",
            evidence={"exception": repr(exc)},
            reasoning="INV-12 day count basis check failed before a verdict could be formed.",
        )


# ---------------------------------------------------------------------------
# Attack registry
# ---------------------------------------------------------------------------

AttackFn = Callable[..., AttackResult]

ATTACKS: dict[str, Callable[[FundingClient], AttackResult]] = {
    "duplicate_funding": attack_duplicate_funding,                           # INV-01
    "closed_case_funding": attack_closed_case_funding,                       # INV-02
    "disburse_without_attorney_ack": attack_disburse_without_attorney_ack,   # INV-03
    "interest_from_application_date": attack_interest_from_application_date, # INV-04
    "exceeds_case_max_exposure": attack_exceeds_case_max_exposure,           # INV-05
    "usury_rate_cap": attack_usury_rate_cap,                                 # INV-06
    "waterfall_priority": attack_waterfall_priority,                         # INV-07
    "lien_balance_exceeds_billed": attack_lien_balance_exceeds_billed,       # INV-08
    "negative_plaintiff_remainder": attack_negative_plaintiff_remainder,     # INV-09
    "cancelled_application_capacity_leak": attack_cancelled_application_capacity_leak,  # INV-10
    "float_payoff": attack_float_payoff,                                     # INV-11
    "interest_day_count_basis": attack_interest_day_count_basis,             # INV-12 (bonus -- was 11 attacks, this is the 11th unique invariant)
}
