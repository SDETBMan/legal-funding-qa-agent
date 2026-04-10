from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from agent.adversary.attacks import AttackResult, attack_duplicate_funding
from agent.clients.funding_client import FundingClient

_ROOT = Path(__file__).resolve().parent.parent

class RunAttackState(TypedDict, total=False):
    """LangGraph state: attack name in, serialized result out."""

    attack_name: str
    result: dict[str, Any]

_ATTACK_REGISTRY: dict[str, Callable[[FundingClient], AttackResult]] = {
    "duplicate_funding": attack_duplicate_funding,
}

KNOWN_ATTACKS: frozenset[str] = frozenset(_ATTACK_REGISTRY.keys())

def _write_attacks_json(attack_name: str, result: AttackResult) -> None:
    artifacts_dir = _ROOT / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    payload = {"attack": attack_name, "result": result.model_dump(mode="json")}
    (artifacts_dir / "attacks.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

def build_run_attack_graph(client: FundingClient):
    """Single-node graph: ``run_attack`` dispatches by name and writes ``artifacts/attacks.json``."""

    def run_attack_node(state: RunAttackState) -> RunAttackState:
        name = state["attack_name"]
        fn = _ATTACK_REGISTRY[name]
        result = fn(client)
        _write_attacks_json(name, result)
        return {"attack_name": name, "result": result.model_dump(mode="json")}

    graph = StateGraph(RunAttackState)
    graph.add_node("run_attack", run_attack_node)
    graph.set_entry_point("run_attack")
    graph.add_edge("run_attack", END)
    return graph.compile()

def run_named_attack(client: FundingClient, attack_name: str) -> dict[str, Any]:
    """Compile and invoke the run_attack graph for ``attack_name``."""
    app = build_run_attack_graph(client)
    return app.invoke({"attack_name": attack_name})

def build_qa_graph() -> Any:
    """
    LangGraph wiring: explorer → swarm → adversary → judge (§3).

    End-to-end coverage maps to API invariants INV-01–INV-12, UI INV-13–INV-16, and eval INV-17–INV-20.
    """
    raise NotImplementedError

def run_graph(state: dict[str, Any]) -> dict[str, Any]:
    """INV-01–INV-20: Execute the compiled QA graph with initial state and return terminal state."""
    raise NotImplementedError
