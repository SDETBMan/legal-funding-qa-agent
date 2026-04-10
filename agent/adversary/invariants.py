"""Canonical invariant identifiers INV-01–INV-20 (§5). Edit ordering only with team review."""

from __future__ import annotations

INVARIANT_IDS: tuple[str, ...] = tuple(f"INV-{i:02d}" for i in range(1, 21))

def invariant_description(invariant_id: str) -> str:
    """INV-01–INV-20: Return the prose rule text for a canonical invariant ID."""
    raise NotImplementedError

def api_invariant_ids() -> tuple[str, ...]:
    """INV-01–INV-12: Financial and legal API-layer invariant IDs."""
    raise NotImplementedError

def ui_invariant_ids() -> tuple[str, ...]:
    """INV-13–INV-16: UI consistency invariant IDs."""
    raise NotImplementedError

def eval_invariant_ids() -> tuple[str, ...]:
    """INV-17–INV-20: Agent and eval-layer invariant IDs."""
    raise NotImplementedError
