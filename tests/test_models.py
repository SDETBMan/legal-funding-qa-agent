from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError

from agent.models.case import Case, CaseStatus, Jurisdiction
from agent.models.disbursement import (
    SettlementDisbursement,
    WaterfallLineItem,
    WaterfallResult,
)
from agent.models.funding import FundingApplication, FundingContract, Payoff
from agent.models.lien import LienPriority, LienRelease, MedicalLien
from agent.models.money import Cents, parse_ui_currency_to_cents, validate_cents

class _CentsBox(BaseModel):
    """Minimal model to exercise ``Cents`` validation."""

    value: Cents

class TestValidateCents:
    def test_accepts_int(self) -> None:
        assert validate_cents(0) == 0
        assert validate_cents(1_234_567) == 1_234_567

    def test_rejects_bool(self) -> None:
        with pytest.raises(TypeError, match="bool"):
            validate_cents(True)
        with pytest.raises(TypeError, match="bool"):
            validate_cents(False)

    def test_rejects_float(self) -> None:
        with pytest.raises(TypeError, match="float"):
            validate_cents(1.0)

    def test_rejects_none(self) -> None:
        with pytest.raises(TypeError, match="None"):
            validate_cents(None)

    def test_accepts_whole_decimal_cents(self) -> None:
        assert validate_cents(Decimal("500000")) == 500_000

    def test_rejects_fractional_decimal_cents(self) -> None:
        with pytest.raises(ValueError, match="whole cents"):
            validate_cents(Decimal("100.5"))

    def test_string_whole_cents_digits(self) -> None:
        assert validate_cents("0") == 0
        assert validate_cents("98765") == 98765

    def test_string_dollars_two_dp(self) -> None:
        assert validate_cents("12.34") == 1234
        assert validate_cents("0.01") == 1

    def test_string_negative_whole_cents(self) -> None:
        assert validate_cents("-100") == -100

    def test_string_rejects_three_decimal_places(self) -> None:
        with pytest.raises(ValueError, match="unrecognized"):
            validate_cents("1.001")

class TestParseUiCurrencyToCents:
    def test_dollar_sign_and_commas(self) -> None:
        assert parse_ui_currency_to_cents("$12,347.50") == 1_234_750

    def test_plain_amount(self) -> None:
        assert parse_ui_currency_to_cents("10.00") == 1000

    def test_parentheses_negative(self) -> None:
        assert parse_ui_currency_to_cents("($50.00)") == -5000

    def test_rejects_invalid(self) -> None:
        with pytest.raises(ValueError):
            parse_ui_currency_to_cents("12.345")

class TestCentsPydanticField:
    def test_rejects_float_in_model(self) -> None:
        with pytest.raises(ValidationError):
            _CentsBox.model_validate({"value": 3.14})

    def test_rejects_bool_in_model(self) -> None:
        with pytest.raises(ValidationError):
            _CentsBox.model_validate({"value": True})

    def test_accepts_int_string(self) -> None:
        m = _CentsBox.model_validate({"value": "42"})
        assert m.value == 42

class TestPayoff:
    def test_total_must_match_components(self) -> None:
        p = Payoff(
            funding_id="F-1",
            principal_cents=100_000,
            accrued_interest_cents=5_000,
            fees_cents=500,
            total_cents=105_500,
        )
        assert p.recompute_total() == 105_500

    def test_mismatch_raises(self) -> None:
        with pytest.raises(ValidationError) as exc:
            Payoff(
                funding_id="F-1",
                principal_cents=100_000,
                accrued_interest_cents=5_000,
                fees_cents=500,
                total_cents=105_501,
            )
        assert "total mismatch" in str(exc.value).lower()

class TestFundingContract:
    def test_negative_approved_raises(self) -> None:
        with pytest.raises(ValidationError):
            FundingContract(
                funding_id="F-1",
                application_id="A-1",
                approved_amount_cents=-1,
                annual_rate_bps=500,
            )

    def test_rate_bps_bounds(self) -> None:
        with pytest.raises(ValidationError):
            FundingContract(
                funding_id="F-1",
                application_id="A-1",
                approved_amount_cents=100,
                annual_rate_bps=-1,
            )

class TestMedicalLien:
    def test_balance_within_bill(self) -> None:
        MedicalLien(
            lien_id="L-1",
            case_id="C-1",
            priority_rank=1,
            balance_cents=50_000,
            original_billed_amount_cents=50_000,
            priority_class=LienPriority.MEDICAL,
        )

    def test_inv_08_excess_balance(self) -> None:
        with pytest.raises(ValidationError) as exc:
            MedicalLien(
                lien_id="L-1",
                case_id="C-1",
                priority_rank=1,
                balance_cents=60_000,
                original_billed_amount_cents=50_000,
                priority_class=LienPriority.MEDICAL,
            )
        assert "INV-08" in str(exc.value)

class TestLienRelease:
    def test_negative_release(self) -> None:
        with pytest.raises(ValidationError):
            LienRelease(lien_id="L-1", release_cents=-1)

class TestSettlementDisbursement:
    def test_buckets_reconcile(self) -> None:
        SettlementDisbursement(
            settlement_id="S-1",
            settlement_amount_cents=1_000_000,
            medicare_medicaid_cents=200_000,
            medical_liens_cents=100_000,
            funding_payoff_cents=400_000,
            attorney_fees_cents=100_000,
            plaintiff_remainder_cents=200_000,
        )

    def test_mismatch_raises(self) -> None:
        with pytest.raises(ValidationError) as exc:
            SettlementDisbursement(
                settlement_id="S-1",
                settlement_amount_cents=100,
                plaintiff_remainder_cents=100,
                funding_payoff_cents=1,
            )
        assert "must equal" in str(exc.value)

    def test_inv_09_negative_remainder(self) -> None:
        with pytest.raises(ValidationError) as exc:
            SettlementDisbursement(
                settlement_id="S-1",
                settlement_amount_cents=100,
                medicare_medicaid_cents=150,
                medical_liens_cents=0,
                funding_payoff_cents=0,
                attorney_fees_cents=0,
                plaintiff_remainder_cents=-50,
            )
        assert "INV-09" in str(exc.value)

class TestWaterfallResult:
    def test_line_item_negative_amount_rejected(self) -> None:
        with pytest.raises(ValidationError):
            WaterfallLineItem(category="x", amount_cents=-1, order_index=0)

    def test_line_items_and_remainder_reconcile(self) -> None:
        WaterfallResult(
            settlement_id="S-1",
            settlement_amount_cents=500_000,
            line_items=[
                WaterfallLineItem(category="medicare", amount_cents=100_000, order_index=0),
                WaterfallLineItem(category="funding", amount_cents=300_000, order_index=1),
            ],
            plaintiff_remainder_cents=100_000,
        )

    def test_total_mismatch(self) -> None:
        with pytest.raises(ValidationError) as exc:
            WaterfallResult(
                settlement_id="S-1",
                settlement_amount_cents=100,
                line_items=[
                    WaterfallLineItem(category="a", amount_cents=50, order_index=0),
                ],
                plaintiff_remainder_cents=60,
            )
        assert "Waterfall mismatch" in str(exc.value)

class TestCaseModel:
    def test_empty_case_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Case(case_id="", status=CaseStatus.ACTIVE, jurisdiction=Jurisdiction.CA)

    def test_negative_exposure(self) -> None:
        with pytest.raises(ValidationError):
            Case(
                case_id="C-1",
                status=CaseStatus.ACTIVE,
                jurisdiction=Jurisdiction.CA,
                case_max_exposure_cents=-1,
            )

class TestFundingApplication:
    def test_uses_cents_validation(self) -> None:
        FundingApplication(
            application_id="A-1",
            case_id="C-1",
            amount_cents=250_000,
            status="PENDING",
        )
        with pytest.raises(ValidationError):
            FundingApplication(
                application_id="A-1",
                case_id="C-1",
                amount_cents=1.5,
                status="PENDING",
            )
