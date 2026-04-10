"""
Money in this codebase is represented exclusively as **integer cents** (INV-11).

Floating-point currency is forbidden: binary floats cannot represent decimal money exactly,
so using them in API bodies or agent logic is an audit and regulatory failure (INV-11).

Accrued interest and payoffs must be derived with **integer arithmetic** on whole cents, with
interest accrual driven by **exact calendar day counts** from disbursement to payoff (INV-12).
Approximate month-based interest at portfolio scale produces material dollar errors; integer
cents plus precise day math keeps recomputations reproducible and defensible.

This module provides the ``Cents`` type alias (semantic ``int``) and ``validate_cents`` for
consistent coercion and rejection rules at API boundaries.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, TypeAlias

Cents: TypeAlias = int
"""Semantic alias for money stored as a whole number of cents (INV-11)."""

def validate_cents(value: Any, field_name: str) -> int:
    """
    Normalize ``value`` to a non-negative integer cent amount.

    Raises ``ValueError`` if:

    * ``value`` is a ``float`` (INV-11 — no float money).
    * ``value`` is a string whose numeric portion has **more than two** digits after the
      decimal point (INV-11 — no ambiguous fractional strings).
    * ``value`` is negative where cents are not permitted (standard monetary fields here).
    * ``value`` is ``bool``, ``None``, or an unsupported type.
    """
    if value is None:
        msg = f"{field_name}: value must not be None"
        raise ValueError(msg)
    if isinstance(value, bool):
        msg = f"{field_name}: bool is not valid for money fields"
        raise ValueError(msg)
    if isinstance(value, float):
        msg = f"{field_name}: float money is forbidden per INV-11"
        raise ValueError(msg)
    if type(value) is int:
        if value < 0:
            msg = f"{field_name}: negative cents are not permitted"
            raise ValueError(msg)
        return value
    if isinstance(value, str):
        return _validate_cents_from_str(value.strip(), field_name)
    if isinstance(value, Decimal):
        if not value.is_finite():
            msg = f"{field_name}: money must be finite"
            raise ValueError(msg)
        if value != value.to_integral_value():
            msg = f"{field_name}: Decimal must represent whole cents"
            raise ValueError(msg)
        iv = int(value)
        if iv < 0:
            msg = f"{field_name}: negative cents are not permitted"
            raise ValueError(msg)
        return iv
    msg = f"{field_name}: unsupported type {type(value).__name__!r} for money"
    raise ValueError(msg)

def _validate_cents_from_str(s: str, field_name: str) -> int:
    if not s:
        msg = f"{field_name}: empty string is not valid money"
        raise ValueError(msg)

    neg = False
    if s[0] == "-":
        neg = True
        s = s[1:].strip()
        if not s:
            msg = f"{field_name}: invalid money string"
            raise ValueError(msg)

    if "." in s:
        whole, frac = s.split(".", 1)
        if not re.fullmatch(r"\d+", whole) or not re.fullmatch(r"\d+", frac):
            msg = f"{field_name}: invalid money string {s!r}"
            raise ValueError(msg)
        if len(frac) > 2:
            msg = (
                f"{field_name}: string money must have at most 2 decimal places "
                f"(INV-11); got {len(frac)} in {s!r}"
            )
            raise ValueError(msg)
        try:
            d = Decimal(s if not neg else f"-{s}")
        except InvalidOperation as e:
            msg = f"{field_name}: invalid decimal money string"
            raise ValueError(msg) from e
        cents = int((d * 100).to_integral_value())
    else:
        if not re.fullmatch(r"\d+", s):
            msg = f"{field_name}: invalid whole-cent string {s!r}"
            raise ValueError(msg)
        cents = int(s)
        if neg:
            cents = -cents

    if cents < 0:
        msg = f"{field_name}: negative cents are not permitted"
        raise ValueError(msg)
    return cents
