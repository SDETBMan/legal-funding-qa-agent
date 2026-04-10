from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from agent.models.case import Case, CaseStatus, Jurisdiction
from agent.models.disbursement import SettlementDisbursement, WaterfallLine
from agent.models.funding import Payoff
from agent.models.lien import LienPriority, LienType
from agent.models.money import validate_cents

class TestValidateCents:
    def test_rejects_float(self) -> None:
        with pytest.raises(ValueError, match="float money is forbidden per INV-11"):
            validate_cents(1.23, "amount_cents")

    def test_rejects_string_more_than_two_decimal_places(self) -> None:
        with pytest.raises(ValueError, match="at most 2 decimal"):
            validate_cents("1.001", "x")

    def test_accepts_valid_int(self) -> None:
        assert validate_cents(0, "n") == 0
        assert validate_cents(99_999, "n") == 99_999

    def test_accepts_valid_string(self) -> None:
        assert validate_cents("100", "n") == 100
        assert validate_cents("12.34", "n") == 1234

    def test_rejects_negative_int(self) -> None:
        with pytest.raises(ValueError, match="negative cents"):
            validate_cents(-1, "n")

class TestPayoff:
    def test_rejects_float_input(self) -> None:
        with pytest.raises(ValidationError) as exc:
            Payoff(
                principal_cents=1.0,
                accrued_interest_cents=0,
                fees_cents=0,
                total_cents=0,
            )
        assert "float money is forbidden per INV-11" in str(exc.value)

    def test_raises_when_total_mismatch_includes_delta(self) -> None:
        with pytest.raises(ValidationError) as exc:
            Payoff(
                principal_cents=100_000,
                accrued_interest_cents=5_000,
                fees_cents=500,
                total_cents=105_501,
            )
        err = str(exc.value)
        assert "delta=" in err
        assert "delta=1" in err.replace(" ", "")

class TestLienPriority:
    def test_raises_when_balance_exceeds_original_billed_with_delta(self) -> None:
        with pytest.raises(ValidationError) as exc:
            LienPriority(
                lien_id="L-1",
                case_id="C-1",
                lien_type=LienType.MEDICAL,
                priority_rank=1,
                balance_cents=60_000,
                original_billed_cents=50_000,
                lienholder_name="Provider",
            )
        assert "INV-08" in str(exc.value)
        assert "delta=" in str(exc.value)

class TestSettlementDisbursement:
    def _line(
        self,
        *,
        rank: int,
        paid: int,
        lt: LienType = LienType.MEDICARE,
        lid: str = "L-1",
    ) -> WaterfallLine:
        return WaterfallLine(
            lien_id=lid,
            lienholder_name="H",
            priority_rank=rank,
            amount_paid_cents=paid,
            lien_type=lt,
        )

    def test_raises_when_remainder_negative(self) -> None:
        with pytest.raises(ValidationError) as exc:
            SettlementDisbursement(
                case_id="C-1",
                settlement_cents=100,
                waterfall=[self._line(rank=1, paid=150)],
                plaintiff_remainder_cents=-50,
            )
        assert "INV-09" in str(exc.value) or "negative cents" in str(exc.value)

def test_funding_application_tz_aware() -> None:
    from agent.models.funding import FundingApplication

    FundingApplication(
        application_id="A-1",
        case_id="C-1",
        amount_cents=100,
        status="PENDING",
        created_at=datetime.now(tz=UTC),
        applicant_name="Jane Doe",
    )
    with pytest.raises(ValidationError):
        FundingApplication(
            application_id="A-1",
            case_id="C-1",
            amount_cents=100,
            status="PENDING",
            created_at=datetime(2020, 1, 1, 12, 0, 0),
            applicant_name="Jane Doe",
        )

def test_settlement_waterfall_must_be_sorted() -> None:
    with pytest.raises(ValidationError, match="sorted by priority_rank"):
        SettlementDisbursement(
            case_id="C-1",
            settlement_cents=100,
            waterfall=[
                WaterfallLine(
                    lien_id="L2",
                    lienholder_name="B",
                    priority_rank=2,
                    amount_paid_cents=50,
                    lien_type=LienType.MEDICAL,
                ),
                WaterfallLine(
                    lien_id="L1",
                    lienholder_name="A",
                    priority_rank=1,
                    amount_paid_cents=50,
                    lien_type=LienType.MEDICARE,
                ),
            ],
            plaintiff_remainder_cents=0,
        )

def test_case_max_exposure_validate_cents() -> None:
    Case(
        case_id="C-1",
        status=CaseStatus.ACTIVE,
        jurisdiction=Jurisdiction.CA,
        case_max_exposure_cents=500_000,
    )
    with pytest.raises(ValidationError):
        Case(
            case_id="C-1",
            status=CaseStatus.ACTIVE,
            jurisdiction=Jurisdiction.CA,
            case_max_exposure_cents=-1,
        )
