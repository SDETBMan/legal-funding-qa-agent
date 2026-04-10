#!/usr/bin/env python3
"""
verify_bugs.py — Smoke test confirming all three intentional bugs
are detectable before running the full QA agent.

Run with:
  python verify_bugs.py

Requires mock API running on localhost:8000.
"""
from __future__ import annotations

import sys
from datetime import date

import httpx

BASE = "http://localhost:8000"


def check(label: str, passed: bool, detail: str) -> bool:
    icon = "✓" if passed else "✗"
    status = "DETECTABLE" if passed else "NOT DETECTABLE — check mock API"
    print(f"  {icon}  {label}: {status}")
    if not passed:
        print(f"     └─ {detail}")
    return passed


def main() -> None:
    print("\nMock API Bug Verification\n" + "=" * 40)

    c = httpx.Client(base_url=BASE, timeout=10.0)

    # Confirm health
    health = c.get("/health").json()
    print(f"\nAPI status: {health['status']}")
    print(f"Known bugs declared: {len(health['known_bugs'])}\n")

    all_passed = True

    # -----------------------------------------------------------------------
    # BUG-01 [INV-11]: total_cents returned as float
    # -----------------------------------------------------------------------
    print("BUG-01 — INV-11: float in payoff total_cents")
    payoff = c.get(
        "/funding/CONTRACT-SEED-001/payoff",
        params={"payoff_date": str(date.today())},
    ).json()
    total = payoff.get("total_cents")
    is_float = isinstance(total, float)
    all_passed &= check(
        "total_cents is float",
        is_float,
        f"Got type={type(total).__name__}, value={total}",
    )
    if is_float:
        print(f"     └─ total_cents={total} (type: {type(total).__name__})")

    # -----------------------------------------------------------------------
    # BUG-02 [INV-04]: interest start date is application_date, not disbursement_date
    # -----------------------------------------------------------------------
    print("\nBUG-02 — INV-04: interest_start_date mismatch")
    interest_start = payoff.get("interest_start_date")
    disbursement_date = payoff.get("disbursement_date")
    dates_differ = interest_start != disbursement_date
    all_passed &= check(
        "interest_start_date != disbursement_date",
        dates_differ,
        f"interest_start_date={interest_start}, disbursement_date={disbursement_date}",
    )
    if dates_differ:
        print(f"     └─ interest accrues from {interest_start}, should be {disbursement_date}")
        from datetime import date as d
        delta = (d.fromisoformat(disbursement_date) - d.fromisoformat(interest_start)).days
        principal = payoff["principal_cents"]
        rate_bps = payoff["rate_bps"]
        overcharge = (principal * rate_bps * delta) // (10_000 * 365)
        print(f"     └─ overcharge: {overcharge} cents (${overcharge/100:.2f}) over {delta} extra days")

    # -----------------------------------------------------------------------
    # BUG-03 [INV-07]: waterfall ignores Medicare super-priority
    # -----------------------------------------------------------------------
    print("\nBUG-03 — INV-07: waterfall does not enforce Medicare super-priority")

    # Create a test case with MEDICAL lien at rank=1, MEDICARE at rank=2
    case = c.post("/cases", json={
        "plaintiff_name": "Bug03 TestPlaintiff",
        "attorney_name": "Bug03 TestAttorney",
        "estimated_settlement_cents": 100_000_00,
        "jurisdiction": "IL",
    }).json()
    cid = case["case_id"]

    c.post("/liens", json={
        "case_id": cid, "lien_type": "MEDICAL",
        "balance_cents": 5_000_00, "original_billed_cents": 5_000_00,
        "lienholder_name": "City Hospital", "priority_rank": 1,  # rank 1 = paid first
    })
    c.post("/liens", json={
        "case_id": cid, "lien_type": "MEDICARE",
        "balance_cents": 3_000_00, "original_billed_cents": 3_000_00,
        "lienholder_name": "CMS", "priority_rank": 2,  # rank 2 = should override to first
    })

    settlement = c.post(f"/cases/{cid}/settle", json={"settlement_cents": 100_000_00}).json()
    waterfall = settlement["waterfall"]

    first_paid = waterfall[0] if waterfall else {}
    medicare_paid_second = (
        len(waterfall) >= 2
        and waterfall[1].get("lien_type") == "MEDICARE"
        and waterfall[0].get("lien_type") == "MEDICAL"
    )
    all_passed &= check(
        "MEDICARE paid after MEDICAL despite lower priority_rank",
        medicare_paid_second,
        f"First paid: {first_paid.get('lien_type')} ({first_paid.get('lienholder_name')})",
    )
    if medicare_paid_second:
        print(f"     └─ Waterfall order: {[w.get('lien_type') for w in waterfall[:3]]}")
        print(f"     └─ MEDICARE at position 1 (0-indexed), should be position 0")

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print("\n" + "=" * 40)
    if all_passed:
        print("All 3 bugs confirmed detectable. QA agent will produce:")
        print("  INV-11 → BREACHED")
        print("  INV-04 → BREACHED")
        print("  INV-07 → BREACHED")
        print("  All others → HELD or INDETERMINATE")
        print("\nReady for demo. Run: python -m agent.main\n")
    else:
        print("One or more bugs NOT detectable. Check mock API implementation.")
        sys.exit(1)


if __name__ == "__main__":
    main()
