from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from agent.adversary.attacks import attack_duplicate_funding
from agent.clients.funding_client import FundingClient

class DuplicateFundingState(TypedDict, total=False):
    """State for the single-node INV-01 duplicate-funding attack graph."""

    result: dict[str, Any]

def _duplicate_funding_node(state: DuplicateFundingState) -> DuplicateFundingState:
    client = FundingClient()
    result = attack_duplicate_funding(client)
    return {"result": result.model_dump(mode="json")}

def build_duplicate_funding_graph():
    """
    Single-node LangGraph: runs ``attack_duplicate_funding`` once, then ends.

    Requires ``MOVEDOCS_API_BASE`` and ``MOVEDOCS_SEED_CASE_ID`` in the environment.
    """
    graph = StateGraph(DuplicateFundingState)
    graph.add_node("duplicate_funding", _duplicate_funding_node)
    graph.set_entry_point("duplicate_funding")
    graph.add_edge("duplicate_funding", END)
    return graph.compile()

def run_duplicate_funding_graph() -> dict[str, Any]:
    """Execute the duplicate-funding graph and return the terminal state (includes ``result``)."""
    app = build_duplicate_funding_graph()
    return app.invoke({})

def build_qa_graph() -> Any:
    """
    LangGraph wiring: explorer → swarm → adversary → judge (§3).

    End-to-end coverage maps to API invariants INV-01–INV-12, UI INV-13–INV-16, and eval INV-17–INV-20.
    """
    raise NotImplementedError

def run_graph(state: dict[str, Any]) -> dict[str, Any]:
    """INV-01–INV-20: Execute the compiled QA graph with initial state and return terminal state."""
    raise NotImplementedError
