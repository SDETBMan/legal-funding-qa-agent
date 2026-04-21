from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, NotRequired, TypedDict

from langgraph.graph import END, StateGraph

from agent.adversary.attacks import ATTACKS, AttackResult
from agent.clients.funding_client import FundingClient
from agent.pii_redactor import get_default_pii_redactor
from agent.run_limits import RunLimits

_ROOT = Path(__file__).resolve().parent.parent


class RunAttackState(TypedDict, total=False):
    """LangGraph state: optional raw PII fields, sanitized copies, attack result out."""

    attack_name: str
    raw_context: NotRequired[str]
    sanitized_context: NotRequired[str]
    raw_payload: NotRequired[dict[str, Any]]
    sanitized_payload: NotRequired[dict[str, Any]]
    pii_entities_found: NotRequired[list[str]]
    pii_redaction_modified: NotRequired[bool]
    rate_limit_summary: NotRequired[dict[str, int]]
    _fallback_config: NotRequired[Any]
    result: dict[str, Any]

_ATTACK_REGISTRY: dict[str, Callable[[FundingClient], AttackResult]] = ATTACKS

KNOWN_ATTACKS: frozenset[str] = frozenset(ATTACKS.keys())

def _write_attacks_json(attack_name: str, result: AttackResult) -> None:
    artifacts_dir = _ROOT / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    payload = {"attack": attack_name, "result": result.model_dump(mode="json")}
    (artifacts_dir / "attacks.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

def build_run_attack_graph(client: FundingClient, run_limits: RunLimits | None = None):
    """
    LangGraph: ``pii_preprocess`` then ``run_attack``.

    Pass ``raw_context`` and/or ``raw_payload`` on invoke to redact before downstream nodes
    read agent-facing text (``sanitized_context`` / ``sanitized_payload``).

    ``run_limits`` bounds node work per run (default: new :class:`RunLimits` per *build*).
    For multiple ``invoke`` calls on one compiled graph, pass the same instance and call
    ``run_limits.reset()`` between invocations, or rebuild the graph with a fresh ``RunLimits``.
    Each node tick counts as one tool call (pipeline step / external I/O style cap).
    """

    limits = run_limits if run_limits is not None else RunLimits()

    def pii_preprocess_node(state: RunAttackState) -> RunAttackState:
        limits.check_and_increment_tool("pii_preprocess")
        redactor = get_default_pii_redactor()
        updates: RunAttackState = {}
        entities: list[str] = []
        modified = False

        raw = state.get("raw_context")
        if isinstance(raw, str) and raw.strip():
            rr = redactor.redact(raw, context="langgraph_raw_context")
            updates["sanitized_context"] = rr.sanitized_text
            entities.extend(rr.entities_found)
            modified = modified or rr.was_modified

        payload = state.get("raw_payload")
        if isinstance(payload, dict) and payload:
            updates["sanitized_payload"] = redactor.redact_dict(payload)
            modified = True

        if entities:
            updates["pii_entities_found"] = entities
        if modified or entities or "sanitized_payload" in updates:
            updates["pii_redaction_modified"] = True
        return updates

    def run_attack_node(state: RunAttackState) -> RunAttackState:
        limits.check_and_increment_tool("run_attack")
        name = state["attack_name"]
        fn = _ATTACK_REGISTRY[name]
        result = fn(client)
        _write_attacks_json(name, result)
        return {
            "attack_name": name,
            "result": result.model_dump(mode="json"),
            "rate_limit_summary": limits.summary(),
        }

    graph = StateGraph(RunAttackState)
    graph.add_node("pii_preprocess", pii_preprocess_node)
    graph.add_node("run_attack", run_attack_node)
    graph.set_entry_point("pii_preprocess")
    graph.add_edge("pii_preprocess", "run_attack")
    graph.add_edge("run_attack", END)
    return graph.compile()


def invoke_run_attack_graph(
    client: FundingClient,
    invoke_state: dict[str, Any],
    run_limits: RunLimits,
) -> dict[str, Any]:
    """Compile the run-attack graph with ``run_limits`` and ``invoke`` with ``invoke_state``."""
    app = build_run_attack_graph(client, run_limits)
    return app.invoke(invoke_state)


def run_named_attack(client: FundingClient, attack_name: str) -> dict[str, Any]:
    """Guardrails preprocessing + graph invoke (convenience for tests and scripts)."""
    from agent.guardrails import prepare_langgraph_invoke

    invoke_state, limits = prepare_langgraph_invoke({"attack_name": attack_name})
    return invoke_run_attack_graph(client, invoke_state, limits)

def build_qa_graph() -> Any:
    """
    LangGraph wiring: explorer → swarm → adversary → judge (§3).

    End-to-end coverage maps to API invariants INV-01–INV-12, UI INV-13–INV-16, and eval INV-17–INV-20.
    """
    raise NotImplementedError

def run_graph(state: dict[str, Any]) -> dict[str, Any]:
    """INV-01–INV-20: Execute the compiled QA graph with initial state and return terminal state."""
    raise NotImplementedError
