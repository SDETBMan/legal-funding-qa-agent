from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent.models.money import Cents

class FundingApplication(BaseModel):
    """INV-01, INV-02, INV-10: Application state and duplicate-active constraints."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    application_id: str
    case_id: str
    amount_cents: Cents = Field(ge=0)
    status: str

class FundingContract(BaseModel):
    """INV-05, INV-06: Approved exposure and rate cap enforcement at approval time."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    funding_id: str
    application_id: str
    approved_amount_cents: Cents = Field(ge=0)
    annual_rate_bps: int = Field(ge=0, le=100_000)

class Payoff(BaseModel):
    """INV-04, INV-11, INV-12: Payoff components; total must match component sum."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    funding_id: str
    principal_cents: Cents = Field(ge=0)
    accrued_interest_cents: Cents = Field(ge=0)
    fees_cents: Cents = Field(ge=0)
    total_cents: Cents = Field(ge=0)

    def recompute_total(self) -> int:
        """INV-04: principal + accrued interest + fees (integer arithmetic only)."""
        return self.principal_cents + self.accrued_interest_cents + self.fees_cents

    @model_validator(mode="after")
    def total_matches_components(self) -> Payoff:
        expected = self.recompute_total()
        if self.total_cents != expected:
            msg = (
                f"Payoff total mismatch: total_cents={self.total_cents}, "
                f"recomputed from components={expected}"
            )
            raise ValueError(msg)
        return self
