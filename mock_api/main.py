"""
mock_api/main.py — Legal Funding Mock API

A self-contained FastAPI server that simulates a legal funding platform
Solutions funding platform. Used for local development and demo runs
of the QA agent.

INTENTIONAL BUGS (the agent must find these):
  BUG-01 [INV-11]: GET /funding/{id}/payoff returns total_cents as float
  BUG-02 [INV-04]: Interest accrues from application_date, not disbursement_date
  BUG-03 [INV-07]: Settlement waterfall does not enforce Medicare super-priority
  BUG-04 [INV-05]: Approve does not re-check case_max_exposure (apply checks it,
                    but approve + amount change could bypass)
  BUG-05 [INV-06]: Seed contract rate_bps (3500) exceeds TX usury cap (1800 bps)
  BUG-06 [INV-08]: Lien balance > original_billed accepted (validator removed)
  BUG-07 [INV-09]: Settlement allows negative plaintiff remainder
  BUG-08 [INV-10]: Cancelled applications do not release reserved capacity

All other invariants are correctly implemented so the agent produces
a mix of BREACHED and HELD results — a realistic demo output.

Run with:
  pip install fastapi uvicorn
  uvicorn mock_api.main:app --reload --port 8000

Or via Docker:
  docker-compose up
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PARK_TZ = ZoneInfo("America/Chicago")
BASE_RATE_BPS = 350          # 3.5% — within all state usury caps
SEED_RATE_BPS = 3500         # 35% — BUG-05: exceeds TX usury cap of 1800 bps
MAX_FUNDING_RATIO = 0.20     # fund up to 20% of estimated case value
STANDARD_FEE_CENTS = 25_00  # $25.00 flat origination fee

app = FastAPI(
    title="Legal Funding Mock API",
    description="Mock platform for QA agent development. Contains intentional invariant violations.",
    version="1.0.0-mock",
)

# ---------------------------------------------------------------------------
# In-memory store (seed data loaded at startup)
# ---------------------------------------------------------------------------

cases: dict[str, dict] = {}
applications: dict[str, dict] = {}
contracts: dict[str, dict] = {}
liens: dict[str, list[dict]] = {}       # case_id -> list of liens
settlements: dict[str, dict] = {}      # case_id -> settlement record
reserved_capacity: dict[str, int] = {}  # case_id -> reserved cents (BUG-08: not released on cancel)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CaseStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SETTLED = "SETTLED"
    DISMISSED = "DISMISSED"
    CLOSED = "CLOSED"

class ApplicationStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DISBURSED = "DISBURSED"
    CANCELLED = "CANCELLED"

class LienType(str, Enum):
    MEDICARE = "MEDICARE"
    MEDICAID = "MEDICAID"
    MEDICAL = "MEDICAL"
    ATTORNEY = "ATTORNEY"

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class CreateCaseRequest(BaseModel):
    plaintiff_name: str
    attorney_name: str
    estimated_settlement_cents: int = Field(gt=0)
    jurisdiction: str = Field(default="IL")

class ApplyRequest(BaseModel):
    case_id: str
    amount_cents: int = Field(gt=0)
    applicant_name: str

class DisburseRequest(BaseModel):
    disbursement_date: date

class CreateLienRequest(BaseModel):
    case_id: str
    lien_type: LienType
    balance_cents: int = Field(gt=0)
    original_billed_cents: int = Field(gt=0)
    lienholder_name: str
    priority_rank: int = Field(ge=1)

    # BUG-06 [INV-08]: Validator intentionally removed — balance_cents > original_billed_cents
    # is accepted. The agent's attack_lien_balance_exceeds_billed must detect this.

class RecordSettlementRequest(BaseModel):
    settlement_cents: int = Field(gt=0)

class AttorneyAckRequest(BaseModel):
    attorney_name: str
    ack_date: date

# ---------------------------------------------------------------------------
# Startup: seed data
# ---------------------------------------------------------------------------

@app.on_event("startup")
def seed_data() -> None:
    """Create realistic seed cases, liens, and one pre-approved contract."""

    # Case 1: Active case — standard scenario
    c1_id = "CASE-001"
    cases[c1_id] = {
        "case_id": c1_id,
        "plaintiff_name": "Maria Santos",
        "attorney_name": "James Holloway",
        "estimated_settlement_cents": 250_000_00,  # $250,000
        "case_max_exposure_cents": 50_000_00,       # $50,000 max exposure
        "jurisdiction": "IL",
        "status": CaseStatus.ACTIVE,
        "created_at": "2025-01-15T09:00:00-06:00",
        "attorney_ack": None,
    }
    liens[c1_id] = [
        {
            "lien_id": "LIEN-001",
            "case_id": c1_id,
            "lien_type": LienType.MEDICARE,
            "priority_rank": 1,
            "balance_cents": 12_500_00,    # $12,500
            "original_billed_cents": 15_000_00,
            "lienholder_name": "Centers for Medicare & Medicaid Services",
        },
        {
            "lien_id": "LIEN-002",
            "case_id": c1_id,
            "lien_type": LienType.MEDICAL,
            "priority_rank": 2,
            "balance_cents": 8_750_00,     # $8,750
            "original_billed_cents": 8_750_00,
            "lienholder_name": "St. Luke's Medical Center",
        },
    ]

    # Case 2: Active case with existing contract (for payoff testing)
    c2_id = "CASE-002"
    cases[c2_id] = {
        "case_id": c2_id,
        "plaintiff_name": "David Kowalski",
        "attorney_name": "Patricia Lee",
        "estimated_settlement_cents": 180_000_00,
        "case_max_exposure_cents": 36_000_00,       # $36,000 max exposure
        "jurisdiction": "TX",
        "status": CaseStatus.ACTIVE,
        "created_at": "2025-02-01T10:00:00-06:00",
        "attorney_ack": {
            "attorney_name": "Patricia Lee",
            "ack_date": "2025-02-05",
        },
    }
    liens[c2_id] = []

    # Pre-seed a disbursed contract on CASE-002 for payoff testing
    app_id_2 = "APP-SEED-001"
    contract_id_2 = "CONTRACT-SEED-001"
    disbursement_date_2 = date(2025, 2, 10)
    application_date_2 = date(2025, 2, 1)  # 9 days before disbursement

    applications[app_id_2] = {
        "application_id": app_id_2,
        "case_id": c2_id,
        "amount_cents": 5_000_00,   # $5,000
        "applicant_name": "David Kowalski",
        "status": ApplicationStatus.DISBURSED,
        "created_at": f"{application_date_2}T09:00:00-06:00",
        "contract_id": contract_id_2,
    }
    contracts[contract_id_2] = {
        "contract_id": contract_id_2,
        "application_id": app_id_2,
        "case_id": c2_id,
        "principal_cents": 5_000_00,
        "rate_bps": SEED_RATE_BPS,                      # BUG-05: 3500 bps exceeds TX cap of 1800
        "application_date": str(application_date_2),    # stored for BUG-02
        "disbursement_date": str(disbursement_date_2),
        "jurisdiction": "TX",
        "status": ApplicationStatus.DISBURSED,
    }

    # Case 3: Settled case — for INV-02 testing (funding on closed case)
    c3_id = "CASE-003"
    cases[c3_id] = {
        "case_id": c3_id,
        "plaintiff_name": "Robert Chen",
        "attorney_name": "Susan Park",
        "estimated_settlement_cents": 95_000_00,
        "case_max_exposure_cents": 19_000_00,       # $19,000 max exposure
        "jurisdiction": "CA",
        "status": CaseStatus.SETTLED,
        "created_at": "2024-11-01T10:00:00-06:00",
        "attorney_ack": None,
    }
    liens[c3_id] = []

    print("[MOCK API] Seed data loaded. Cases: CASE-001, CASE-002, CASE-003")


# ---------------------------------------------------------------------------
# Case endpoints
# ---------------------------------------------------------------------------

@app.get("/cases")
def list_cases() -> list[dict]:
    return list(cases.values())


@app.get("/cases/{case_id}")
def get_case(case_id: str) -> dict:
    if case_id not in cases:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return cases[case_id]


@app.post("/cases", status_code=status.HTTP_201_CREATED)
def create_case(req: CreateCaseRequest) -> dict:
    case_id = f"CASE-{uuid.uuid4().hex[:6].upper()}"
    max_exposure = int(req.estimated_settlement_cents * MAX_FUNDING_RATIO)
    case = {
        "case_id": case_id,
        "plaintiff_name": req.plaintiff_name,
        "attorney_name": req.attorney_name,
        "estimated_settlement_cents": req.estimated_settlement_cents,
        "case_max_exposure_cents": max_exposure,
        "jurisdiction": req.jurisdiction,
        "status": CaseStatus.ACTIVE,
        "created_at": datetime.now(tz=PARK_TZ).isoformat(),
        "attorney_ack": None,
    }
    cases[case_id] = case
    liens[case_id] = []
    return case


@app.post("/cases/{case_id}/attorney-ack")
def record_attorney_ack(case_id: str, req: AttorneyAckRequest) -> dict:
    if case_id not in cases:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    cases[case_id]["attorney_ack"] = {
        "attorney_name": req.attorney_name,
        "ack_date": str(req.ack_date),
    }
    return {"status": "recorded", "case_id": case_id, "ack_date": str(req.ack_date)}


# ---------------------------------------------------------------------------
# Funding endpoints
# ---------------------------------------------------------------------------

@app.post("/funding/apply", status_code=status.HTTP_201_CREATED)
def apply_for_funding(req: ApplyRequest) -> dict:
    """
    INV-01 correctly implemented: rejects duplicate active funding.
    INV-02 correctly implemented: rejects funding on non-ACTIVE cases.
    INV-05 correctly implemented: enforces case max exposure.
    """
    case = cases.get(req.case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {req.case_id} not found")

    # INV-02: reject non-active cases
    if case["status"] != CaseStatus.ACTIVE:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot fund case with status {case['status']}. Only ACTIVE cases are eligible."
        )

    # INV-01: reject if there is already an active application
    for app in applications.values():
        if (
            app["case_id"] == req.case_id
            and app["status"] in (ApplicationStatus.PENDING, ApplicationStatus.APPROVED, ApplicationStatus.DISBURSED)
        ):
            raise HTTPException(
                status_code=409,
                detail=f"Case {req.case_id} already has an active funding application {app['application_id']}."
            )

    # INV-05: enforce case max exposure
    max_exposure = int(case["estimated_settlement_cents"] * MAX_FUNDING_RATIO)
    if req.amount_cents > max_exposure:
        raise HTTPException(
            status_code=422,
            detail=f"Requested amount {req.amount_cents} cents exceeds case max exposure {max_exposure} cents."
        )

    app_id = f"APP-{uuid.uuid4().hex[:8].upper()}"
    application = {
        "application_id": app_id,
        "case_id": req.case_id,
        "amount_cents": req.amount_cents,
        "applicant_name": req.applicant_name,
        "status": ApplicationStatus.PENDING,
        "created_at": datetime.now(tz=PARK_TZ).isoformat(),
        "contract_id": None,
    }
    applications[app_id] = application
    # BUG-08 [INV-10]: Track reserved capacity (but cancel does NOT release it)
    reserved_capacity[req.case_id] = reserved_capacity.get(req.case_id, 0) + req.amount_cents
    return application


@app.post("/funding/{application_id}/approve")
def approve_funding(application_id: str) -> dict:
    """
    BUG-04 [INV-05]: Does NOT re-check case_max_exposure at approval time.
    If the amount was changed between apply and approve, exposure could exceed the cap.
    The attack exploits this by applying for an amount just under the cap on a fresh case
    whose max_exposure is low.
    """
    app = applications.get(application_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application {application_id} not found")
    if app["status"] != ApplicationStatus.PENDING:
        raise HTTPException(status_code=422, detail=f"Application is {app['status']}, not PENDING")

    # BUG-04: No re-check of case_max_exposure_cents here (only checked at apply time)
    app["status"] = ApplicationStatus.APPROVED
    case = cases.get(app["case_id"], {})
    return {
        "application_id": application_id,
        "status": ApplicationStatus.APPROVED,
        "case_max_exposure_cents": case.get("case_max_exposure_cents"),
        "amount_cents": app["amount_cents"],
    }


@app.post("/funding/{application_id}/disburse")
def disburse_funding(application_id: str, req: DisburseRequest) -> dict:
    """
    INV-03 correctly implemented: blocks disbursement without attorney ack.
    Creates a contract on successful disbursement.
    """
    app = applications.get(application_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application {application_id} not found")
    if app["status"] != ApplicationStatus.APPROVED:
        raise HTTPException(status_code=422, detail=f"Application must be APPROVED before disbursing")

    case = cases[app["case_id"]]

    # INV-03: require attorney acknowledgment
    if not case.get("attorney_ack"):
        raise HTTPException(
            status_code=422,
            detail="Attorney acknowledgment required before disbursement. Record ack via POST /cases/{id}/attorney-ack first."
        )

    contract_id = f"CONTRACT-{uuid.uuid4().hex[:8].upper()}"
    contract = {
        "contract_id": contract_id,
        "application_id": application_id,
        "case_id": app["case_id"],
        "principal_cents": app["amount_cents"],
        "rate_bps": BASE_RATE_BPS,
        "application_date": app["created_at"][:10],     # YYYY-MM-DD stored for BUG-02
        "disbursement_date": str(req.disbursement_date),
        "jurisdiction": case.get("jurisdiction", "IL"),
        "status": ApplicationStatus.DISBURSED,
    }
    contracts[contract_id] = contract
    app["status"] = ApplicationStatus.DISBURSED
    app["contract_id"] = contract_id

    return {
        "contract_id": contract_id,
        "application_id": application_id,
        "principal_cents": app["amount_cents"],
        "disbursement_date": str(req.disbursement_date),
        "status": "DISBURSED",
    }


@app.get("/funding/{contract_id}/payoff")
def get_payoff(contract_id: str, payoff_date: date) -> dict[str, Any]:
    """
    INTENTIONAL BUG — BUG-01 [INV-11]:
        total_cents is returned as a Python float, not an int.
        This violates INV-11: all money fields must be integer cents.
        The agent's attack_float_payoff must detect this.

    INTENTIONAL BUG — BUG-02 [INV-04]:
        Interest is computed from application_date, not disbursement_date.
        This overcharges the plaintiff by the number of days between
        application and disbursement (typically 3-14 days).
        The agent's attack_interest_from_application_date must detect this.
    """
    contract = contracts.get(contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail=f"Contract {contract_id} not found")

    principal = contract["principal_cents"]
    rate_bps = contract["rate_bps"]

    # BUG-02 [INV-04]: should use disbursement_date, using application_date instead
    wrong_start_date = date.fromisoformat(contract["application_date"])     # WRONG
    correct_start_date = date.fromisoformat(contract["disbursement_date"])  # CORRECT (unused)

    days_elapsed = (payoff_date - wrong_start_date).days  # inflated by days between app and disburse

    # Integer interest math — correct formula, wrong start date
    interest_cents = (principal * rate_bps * days_elapsed) // (10_000 * 365)

    total = principal + interest_cents + STANDARD_FEE_CENTS

    return {
        "contract_id": contract_id,
        "principal_cents": principal,
        "accrued_interest_cents": interest_cents,
        "fees_cents": STANDARD_FEE_CENTS,
        # BUG-01 [INV-11]: float() call poisons the total — should be int(total)
        "total_cents": float(total),        # INTENTIONAL BUG: float contamination
        "payoff_date": str(payoff_date),
        "days_elapsed": days_elapsed,
        "rate_bps": rate_bps,
        # Include both dates so the agent can see the discrepancy
        "interest_start_date": str(wrong_start_date),
        "disbursement_date": contract["disbursement_date"],
    }


@app.post("/funding/{application_id}/cancel")
def cancel_funding(application_id: str) -> dict:
    app = applications.get(application_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application {application_id} not found")
    if app["status"] in (ApplicationStatus.DISBURSED,):
        raise HTTPException(status_code=422, detail="Cannot cancel a disbursed application")
    app["status"] = ApplicationStatus.CANCELLED
    return {"application_id": application_id, "status": ApplicationStatus.CANCELLED}


@app.get("/funding")
def list_applications(case_id: str | None = None) -> list[dict]:
    result = list(applications.values())
    if case_id:
        result = [a for a in result if a["case_id"] == case_id]
    return result


@app.get("/funding/{application_id}")
def get_application(application_id: str) -> dict:
    app = applications.get(application_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application {application_id} not found")
    return app


@app.get("/contracts/{contract_id}")
def get_contract(contract_id: str) -> dict:
    contract = contracts.get(contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail=f"Contract {contract_id} not found")
    return contract


@app.get("/cases/{case_id}/capacity")
def get_case_capacity(case_id: str) -> dict:
    """Returns reserved and available capacity for a case (INV-10 testing)."""
    if case_id not in cases:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    case = cases[case_id]
    max_exp = case.get("case_max_exposure_cents", 0)
    reserved = reserved_capacity.get(case_id, 0)
    return {
        "case_id": case_id,
        "case_max_exposure_cents": max_exp,
        "reserved_cents": reserved,
        "available_cents": max(0, max_exp - reserved),
    }


# ---------------------------------------------------------------------------
# Lien endpoints
# ---------------------------------------------------------------------------

@app.post("/liens", status_code=status.HTTP_201_CREATED)
def create_lien(req: CreateLienRequest) -> dict:
    if req.case_id not in cases:
        raise HTTPException(status_code=404, detail=f"Case {req.case_id} not found")

    lien_id = f"LIEN-{uuid.uuid4().hex[:6].upper()}"
    lien = {
        "lien_id": lien_id,
        "case_id": req.case_id,
        "lien_type": req.lien_type,
        "priority_rank": req.priority_rank,
        "balance_cents": req.balance_cents,
        "original_billed_cents": req.original_billed_cents,
        "lienholder_name": req.lienholder_name,
    }
    liens.setdefault(req.case_id, []).append(lien)
    return lien


@app.get("/cases/{case_id}/liens")
def get_liens(case_id: str) -> list[dict]:
    if case_id not in cases:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return liens.get(case_id, [])


# ---------------------------------------------------------------------------
# Settlement disbursement endpoint
# ---------------------------------------------------------------------------

@app.post("/cases/{case_id}/settle")
def record_settlement(case_id: str, req: RecordSettlementRequest) -> dict:
    """
    INTENTIONAL BUG — BUG-03 [INV-07]:
        Waterfall is sorted by priority_rank ascending, which is correct
        in principle — BUT Medicare/Medicaid liens (super-priority) are
        NOT treated specially. If a MEDICAL lien has priority_rank=1
        and a MEDICARE lien has priority_rank=2, Medicare will be paid
        second. This violates INV-07.

        The correct behavior: always pay MEDICARE and MEDICAID liens
        before any other lien type, regardless of priority_rank.

        The agent's attack_waterfall_priority must detect this by
        constructing a scenario where a MEDICAL lien has rank=1
        and MEDICARE has rank=2.
    """
    if case_id not in cases:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    case = cases[case_id]
    case_liens = liens.get(case_id, [])

    # Find disbursed contract for this case (if any)
    case_contracts = [
        c for c in contracts.values()
        if c["case_id"] == case_id and c["status"] == ApplicationStatus.DISBURSED
    ]

    settlement = req.settlement_cents
    waterfall_lines = []
    running_total = 0

    # BUG-03 [INV-07]: sorts only by priority_rank — does NOT enforce
    # Medicare/Medicaid super-priority over other lien types.
    # Correct implementation would sort by: (0 if federal else 1, priority_rank)
    sorted_liens = sorted(case_liens, key=lambda x: x["priority_rank"])   # INTENTIONAL BUG

    for lien in sorted_liens:
        # BUG-07 [INV-09]: pays full lien balance without checking if settlement
        # covers it.  Correct implementation would cap at remaining funds and reject
        # (or flag) when total obligations exceed settlement.
        pay_amount = lien["balance_cents"]
        waterfall_lines.append({
            "lien_id": lien["lien_id"],
            "lienholder_name": lien["lienholder_name"],
            "lien_type": lien["lien_type"],
            "priority_rank": lien["priority_rank"],
            "amount_paid_cents": pay_amount,
        })
        running_total += pay_amount

    # Pay funding contracts after liens
    for contract in case_contracts:
        today = date.today()
        payoff_date = today
        start = date.fromisoformat(contract["disbursement_date"])
        days = (payoff_date - start).days
        principal = contract["principal_cents"]
        rate_bps = contract["rate_bps"]
        interest = (principal * rate_bps * days) // (10_000 * 365)
        payoff = principal + interest + STANDARD_FEE_CENTS

        pay_amount = min(payoff, settlement - running_total)
        waterfall_lines.append({
            "contract_id": contract["contract_id"],
            "lienholder_name": "Legal Funding Company",
            "lien_type": "FUNDING_PAYOFF",
            "amount_paid_cents": pay_amount,
        })
        running_total += pay_amount

    plaintiff_remainder = settlement - running_total

    result = {
        "case_id": case_id,
        "settlement_cents": settlement,
        "waterfall": waterfall_lines,
        "total_disbursed_cents": running_total,
        "plaintiff_remainder_cents": plaintiff_remainder,
        "plaintiff_remainder_valid": plaintiff_remainder >= 0,
    }

    settlements[case_id] = result
    cases[case_id]["status"] = CaseStatus.SETTLED

    return result


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "note": "Mock API — contains intentional invariant violations for QA agent demo",
        "known_bugs": [
            "BUG-01 [INV-11]: GET /funding/{id}/payoff returns total_cents as float",
            "BUG-02 [INV-04]: Interest accrues from application_date, not disbursement_date",
            "BUG-03 [INV-07]: Waterfall does not enforce Medicare/Medicaid super-priority",
            "BUG-04 [INV-05]: Approve does not re-check case_max_exposure",
            "BUG-05 [INV-06]: Seed contract rate_bps (3500) exceeds TX usury cap (1800 bps)",
            "BUG-06 [INV-08]: Lien balance > original_billed accepted",
            "BUG-07 [INV-09]: Settlement allows negative plaintiff remainder",
            "BUG-08 [INV-10]: Cancelled applications do not release reserved capacity",
        ],
        "seed_data": {
            "cases": list(cases.keys()),
            "seeded_contract": "CONTRACT-SEED-001 on CASE-002",
        },
    }
