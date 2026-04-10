from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator, model_validator

from agent.models.money import validate_cents

class FundingApplication(BaseModel):
    """Funding application submitted against a case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    application_id: str
    case_id: str
    amount_cents: int
    status: str
    created_at: datetime
    applicant_name: str

    @field_validator("amount_cents", mode="before")
    @classmethod
    def _amount_cents(cls, v: Any, info: ValidationInfo) -> int:
        return validate_cents(v, info.field_name or "amount_cents")

    @field_validator("created_at")
    @classmethod
    def _created_at_tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            msg = "created_at must be timezone-aware"
            raise ValueError(msg)
        return v

class FundingContract(BaseModel):
    """Executed funding contract linked to an application."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_id: str
    application_id: str
    principal_cents: int
    rate_bps: int
    disbursement_date: date
    status: str

    @field_validator("principal_cents", mode="before")
    @classmethod
    def _principal_cents(cls, v: Any, info: ValidationInfo) -> int:
        return validate_cents(v, info.field_name or "principal_cents")

class Payoff(BaseModel):
    """INV-04, INV-11, INV-12: Payoff components; ``total_cents`` must match integer sum."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    principal_cents: int
    accrued_interest_cents: int
    fees_cents: int
    total_cents: int

    @field_validator(
        "principal_cents",
        "accrued_interest_cents",
        "fees_cents",
        "total_cents",
        mode="before",
    )
    @classmethod
    def _money_fields(cls, v: Any, info: ValidationInfo) -> int:
        name = info.field_name or "cents"
        return validate_cents(v, name)

    def recompute_total(self) -> int:
        """INV-04: principal + accrued interest + fees using integer arithmetic only."""
        return self.principal_cents + self.accrued_interest_cents + self.fees_cents

    @model_validator(mode="after")
    def total_must_match(self) -> Payoff:
        expected = self.recompute_total()
        if self.total_cents != expected:
            delta = self.total_cents - expected
            msg = (
                f"Payoff total mismatch: total_cents={self.total_cents}, "
                f"recomputed={expected}, delta={delta}"
            )
            raise ValueError(msg)
        return self
