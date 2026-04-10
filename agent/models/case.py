from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent.models.money import validate_cents

class CaseStatus(str, Enum):
    """INV-02: Terminal states must block new funding approvals."""

    ACTIVE = "ACTIVE"
    SETTLED = "SETTLED"
    DISMISSED = "DISMISSED"
    CLOSED = "CLOSED"

class Jurisdiction(str, Enum):
    """INV-06: Jurisdiction drives applicable usury caps from config, not hardcoded rates."""

    AL = "AL"
    AK = "AK"
    AZ = "AZ"
    CA = "CA"
    TX = "TX"
    NY = "NY"
    OTHER = "OTHER"

class Case(BaseModel):
    """
    INV-02: Case status gates funding lifecycle decisions.
    INV-05: Optional ``case_max_exposure_cents`` for credit limit semantics.
    INV-14: Canonical case status for UI/API consistency checks.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1)
    status: CaseStatus
    jurisdiction: Jurisdiction
    case_max_exposure_cents: int | None = None

    @model_validator(mode="after")
    def exposure_non_negative_when_set(self) -> Case:
        if self.case_max_exposure_cents is not None:
            validate_cents(self.case_max_exposure_cents, "case_max_exposure_cents")
        return self
