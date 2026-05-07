from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import agentops
import structlog

from agent.adversary.attacks import ATTACKS, AttackResult
from agent.clients.funding_client import FundingClient
from agent.guardrails import create_guarded_agent_state, fallback_config, prepare_langgraph_invoke
from agent.graph import KNOWN_ATTACKS, invoke_run_attack_graph
from agent.pii_redactor import PIIRedactor
from agent.retry_policy import with_retry
from agent.run_limits import RateLimitExceeded, RunLimits
from judge.drift_check import log_judge_prompt_drift_warnings
from judge.prompts import get_prompt_fingerprints, write_baseline_file
from guardrails.summarization_middleware import SummarizationMiddleware
from guardrails.tool_selector_middleware import ToolSelectorMiddleware, ToolSpec

log = structlog.get_logger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_ARTIFACTS = _ROOT / "artifacts"

# TraceContext from start_trace (AgentOps v4); passed to end_trace.
_agentops_trace_ref: Any = None

# §12.1 severity tiers (CLAUDE.md)
_CRITICAL_RULES = frozenset(
    {"INV-04", "INV-06", "INV-07", "INV-09", "INV-11", "INV-13"}
)
_HIGH_RULES = frozenset({"INV-01", "INV-02", "INV-03", "INV-08", "INV-12", "INV-15"})
_MEDIUM_RULES = frozenset({"INV-05", "INV-10", "INV-14", "INV-16"})
_EVAL_RULES = frozenset({"INV-17", "INV-18", "INV-19", "INV-20"})


def _severity_for_rule(rule: str) -> str:
    if rule in _CRITICAL_RULES:
        return "CRITICAL"
    if rule in _HIGH_RULES:
        return "HIGH"
    if rule in _MEDIUM_RULES:
        return "MEDIUM"
    if rule in _EVAL_RULES:
        return "EVAL"
    return "HIGH"


def _redact_api_base(raw: str) -> str:
    if not raw:
        return "redacted"
    return "redacted"


def _adversarial_entry(attack_name: str, result: AttackResult) -> dict[str, Any]:
    return {
        "rule": result.rule,
        "name": attack_name,
        "severity": _severity_for_rule(result.rule),
        "status": result.status,
        "evidence": result.evidence,
        "reasoning": result.reasoning,
    }


def _compute_release_recommendation(adversarial: list[dict[str, Any]]) -> dict[str, Any]:
    breached = [a for a in adversarial if a.get("status") == "BREACHED"]
    crit_b = [a for a in breached if a.get("severity") == "CRITICAL"]
    high_b = [a for a in breached if a.get("severity") == "HIGH"]
    med_b = [a for a in breached if a.get("severity") == "MEDIUM"]
    eval_b = [a for a in breached if a.get("severity") == "EVAL"]

    blocking_rules = sorted({a["rule"] for a in crit_b + high_b})

    if crit_b or high_b:
        parts = []
        if crit_b:
            parts.append(f'{len(crit_b)} CRITICAL breach(es): {", ".join(a["rule"] for a in crit_b)}')
        if high_b:
            parts.append(f'{len(high_b)} HIGH breach(es): {", ".join(a["rule"] for a in high_b)}')
        return {
            "decision": "BLOCK",
            "reason": "; ".join(parts),
            "override_required": bool(high_b) and not bool(crit_b),
            "blocking_rules": blocking_rules,
        }
    if med_b:
        return {
            "decision": "WARN",
            "reason": f'MEDIUM tier breach(es): {", ".join(a["rule"] for a in med_b)} — deploy may proceed with alert.',
            "override_required": False,
            "blocking_rules": [],
        }
    if eval_b:
        return {
            "decision": "PASS",
            "reason": "EVAL-layer breach(es) logged; no release block per §12.1.",
            "override_required": False,
            "blocking_rules": [],
        }
    return {
        "decision": "PASS",
        "reason": "No adversarial breaches; release gate clear.",
        "override_required": False,
        "blocking_rules": [],
    }


def _summary_block(adversarial: list[dict[str, Any]], release: dict[str, Any]) -> dict[str, Any]:
    held = sum(1 for a in adversarial if a.get("status") == "HELD")
    breached = sum(1 for a in adversarial if a.get("status") == "BREACHED")
    indeterminate = sum(1 for a in adversarial if a.get("status") == "INDETERMINATE")
    critical_breaches = sum(
        1 for a in adversarial if a.get("status") == "BREACHED" and a.get("severity") == "CRITICAL"
    )
    high_breaches = sum(
        1 for a in adversarial if a.get("status") == "BREACHED" and a.get("severity") == "HIGH"
    )

    headline = release.get("reason", "")
    if release["decision"] == "PASS" and breached == 0:
        headline = f"All {held} adversarial checks held or indeterminate; no breaches."

    return {
        "held": held,
        "breached": breached,
        "indeterminate": indeterminate,
        "critical_breaches": critical_breaches,
        "high_breaches": high_breaches,
        "headline": headline,
    }


def _build_report(
    *,
    api_base_raw: str,
    adversarial: list[dict[str, Any]],
) -> dict[str, Any]:
    release = _compute_release_recommendation(adversarial)
    summary = _summary_block(adversarial, release)
    started = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    return {
        "run_id": str(uuid.uuid4()),
        "started_at": started,
        "api_base": _redact_api_base(api_base_raw),
        "prompt_versions": {
            k: f"sha256:{fp['sha256']}"
            for k, fp in get_prompt_fingerprints().items()
        },
        "happy_path": {
            "status": "SKIP",
            "funding_id": "",
            "steps": [],
        },
        "adversarial": adversarial,
        "ui_reconciliation": [],
        "eval_layer": [],
        "summary": summary,
        "release_recommendation": release,
    }


def _write_report(report: dict[str, Any]) -> None:
    _ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = _ARTIFACTS / "report.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _print_summary_table(adversarial: list[dict[str, Any]]) -> None:
    """Human table plus structured log lines (§12-style rows)."""
    if not adversarial:
        print("(no adversarial rows)")
        return
    headers = ("rule", "name", "severity", "status", "reasoning")
    rows = [
        (
            a["rule"],
            a["name"],
            a["severity"],
            a["status"],
            (a.get("reasoning") or "")[:120],
        )
        for a in adversarial
    ]
    widths = [max(len(h), *(len(str(r[i])) for r in rows)) for i, h in enumerate(headers)]
    line = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    sep = "-+-".join("-" * widths[i] for i in range(len(headers)))
    print(line)
    print(sep)
    for r in rows:
        print(" | ".join(str(r[i]).ljust(widths[i]) for i in range(len(headers))))
    for a in adversarial:
        log.info(
            "qa_adversarial_attack_summary",
            rule=a["rule"],
            name=a["name"],
            severity=a["severity"],
            status=a["status"],
            reasoning=a.get("reasoning", ""),
        )


def _agentops_enabled() -> bool:
    return bool(os.environ.get("AGENTOPS_API_KEY"))


def _agentops_init() -> None:
    key = os.environ.get("AGENTOPS_API_KEY")
    if not key:
        return
    try:
        agentops.init(key, auto_start_session=False)
    except TypeError:
        try:
            agentops.init(key)
        except Exception:
            pass
    except Exception:
        pass


def _agentops_start_trace() -> None:
    global _agentops_trace_ref
    if not _agentops_enabled():
        return
    try:
        _agentops_trace_ref = agentops.start_trace(
            trace_name="legal-funding-qa",
            tags=["legal-funding-qa", "invariant-attack"],
        )
    except Exception:
        _agentops_trace_ref = None


def _agentops_end_trace(decision: str) -> None:
    if not _agentops_enabled():
        return
    try:
        end_state = "Error" if decision == "BLOCK" else "Success"
        agentops.end_trace(_agentops_trace_ref, end_state=end_state)
    except Exception:
        pass


def _agentops_session_url() -> str | None:
    if not _agentops_enabled():
        return None
    ref = _agentops_trace_ref
    if ref is not None:
        for attr in ("session_url", "url", "replay_url", "trace_url"):
            url = getattr(ref, attr, None)
            if isinstance(url, str) and url:
                return url
        sid = getattr(ref, "session_id", None) or getattr(ref, "trace_id", None)
        if isinstance(sid, str) and sid:
            base = os.environ.get("AGENTOPS_APP_URL", "https://app.agentops.ai").rstrip("/")
            return f"{base}/sessions/{sid}"
        if isinstance(ref, str):
            base = os.environ.get("AGENTOPS_APP_URL", "https://app.agentops.ai").rstrip("/")
            return f"{base}/sessions/{ref}"
    try:
        client = agentops.get_client()
        for attr in ("session_url", "current_session_url", "replay_url"):
            url = getattr(client, attr, None)
            if isinstance(url, str) and url:
                return url
    except Exception:
        pass
    return None


def run_guardrails_smoke_test() -> dict[str, Any]:
    """
    Standalone demo: synthetic PII + funding cents through guardrails and one rate-limit tick.

    Does not call the LangGraph. Does not require ``FUNDING_API_BASE``.
    """
    raw_payload: dict[str, Any] = {
        "plaintiff_ssn": "123-45-6789",
        "plaintiff_email": "plaintiff@example.com",
        "funding_amount_cents": 500_000,
        "memo": "Reach plaintiff@example.com about the 123-45-6789 file before funding.",
    }

    guarded = create_guarded_agent_state(raw_payload)
    limits = guarded["_run_limits"]
    limits.check_and_increment_tool("smoke_test")

    print("--- guardrails smoke test ---")
    print("Original payload (sensitive fields):")
    print(f"  plaintiff_ssn: {raw_payload['plaintiff_ssn']!r}")
    print(f"  plaintiff_email: {raw_payload['plaintiff_email']!r}")
    print(f"  funding_amount_cents: {raw_payload['funding_amount_cents']} (integer cents, INV-11)")
    print(f"  memo: {raw_payload['memo']!r}")
    print()
    print("After create_guarded_agent_state() (string values redacted where detected):")
    for key in ("plaintiff_ssn", "plaintiff_email", "memo"):
        print(f"  {key}: {guarded.get(key, '')!r}")
    print(f"  funding_amount_cents: {guarded.get('funding_amount_cents')!r} (unchanged; not a str field)")
    print()
    print("limits.summary():")
    print(json.dumps(limits.summary(), indent=2))
    print("--- end smoke test ---")

    # ---------------------------------------------------------------------
    # Demo: ToolSelectorMiddleware (heuristic mode; always keep search)
    # ---------------------------------------------------------------------
    selector = ToolSelectorMiddleware(llm=None, fast_model="claude-haiku", max_tools=3)
    sample_tools = [
        ToolSpec(name="search", description="Search docs/code for relevant references.", is_search=True),
        ToolSpec(name="api_validate", description="Call API and validate payoff calculation fields."),
        ToolSpec(name="playwright_execute", description="Run Playwright flow to verify payoff shown in UI."),
        ToolSpec(name="db_query", description="Run a SQL query for the funding application."),
        ToolSpec(name="email_notify", description="Send an email to stakeholders about the run."),
        ToolSpec(name="artifact_write", description="Write artifacts/report.json to disk."),
    ]
    sample_goal = "validate funding application payoff calculation"

    print()
    print("--- tool selector middleware demo ---")
    print(f"Goal: {sample_goal!r}")
    print("Tools BEFORE:")
    for t in sample_tools:
        print(f"  - {t.name}{' (search)' if t.is_search else ''}: {t.description}")

    async def _run_tool_select() -> list[ToolSpec]:
        return await selector.select_tools(goal=sample_goal, tools=sample_tools, trace_context={"demo": "guardrails"})

    selected = asyncio.run(_run_tool_select())

    print("Tools AFTER (top 3, always including search):")
    for t in selected:
        print(f"  - {t.name}{' (search)' if t.is_search else ''}: {t.description}")
    print("--- end tool selector demo ---")

    # ---------------------------------------------------------------------
    # Demo: SummarizationMiddleware (heuristic mode; triggers with small window)
    # ---------------------------------------------------------------------
    summarizer = SummarizationMiddleware(
        llm=None,
        fast_model="claude-haiku",
        context_window_tokens=250,
        trigger_ratio=0.80,
        keep_last_n=20,
    )
    # Create 25 messages with enough content to exceed the small token window.
    sample_history: list[dict[str, str]] = []
    for i in range(25):
        role = "user" if i % 2 == 0 else "assistant"
        content = (
            f"message {i}: validate payoff calculation invariant INV-04 and cents integrity INV-11. "
            "Include context about disbursement_date day count and payoff recomputation. "
            + ("x" * 120)
        )
        sample_history.append({"role": role, "content": content})

    print()
    print("--- summarization middleware demo ---")
    print(f"Messages BEFORE: {len(sample_history)}")
    print(f"Estimated tokens BEFORE: {summarizer.estimate_tokens(sample_history)}")
    print("First 2 messages BEFORE:")
    for m in sample_history[:2]:
        print(f"  - {m['role']}: {m['content'][:90]}...")
    print("Last 2 messages BEFORE:")
    for m in sample_history[-2:]:
        print(f"  - {m['role']}: {m['content'][:90]}...")

    async def _run_summarize() -> list[dict[str, str]]:
        return await summarizer.maybe_summarize(messages=sample_history, trace_context={"demo": "guardrails"})

    summarized = asyncio.run(_run_summarize())

    print(f"Messages AFTER: {len(summarized)}")
    print(f"Estimated tokens AFTER: {summarizer.estimate_tokens(summarized)}")
    print("First 2 messages AFTER:")
    for m in summarized[:2]:
        print(f"  - {m['role']}: {m['content'][:120]}...")
    print("Last 2 messages AFTER (should match last two of BEFORE):")
    for m in summarized[-2:]:
        print(f"  - {m['role']}: {m['content'][:90]}...")
    print("--- end summarization demo ---")

    return guarded


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m agent.main")
    parser.add_argument(
        "--demo-guardrails",
        action="store_true",
        help="Run PII + rate-limit smoke demo and exit (no API, no graph).",
    )
    parser.add_argument(
        "--write-judge-baseline",
        action="store_true",
        help="Write config/judge_prompt_baseline.json from judge.prompts (hashlib SHA-256) and exit.",
    )
    parser.add_argument(
        "--skip-prompt-check",
        action="store_true",
        help="Skip pre-deploy judge prompt drift check (Drift Triangle).",
    )
    parser.add_argument(
        "--attack",
        type=str,
        default=None,
        metavar="NAME",
        help="Run a single attack by name. Omit to run all registered attacks and write report.json.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """
    CLI entry point for the QA agent (§3).

    Orchestrates the reliability charter; release artifacts reflect INV-01–INV-20 findings.
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if args.demo_guardrails:
        run_guardrails_smoke_test()
        raise SystemExit(0)

    if args.write_judge_baseline:
        path = write_baseline_file()
        print(f"wrote judge prompt baseline: {path}")
        raise SystemExit(0)

    if not args.skip_prompt_check:
        log_judge_prompt_drift_warnings()

    if "FUNDING_API_BASE" not in os.environ:
        print("error: FUNDING_API_BASE is not set", file=sys.stderr)
        raise SystemExit(1)

    _agentops_init()
    _agentops_start_trace()

    if args.attack is None:
        _run_all_attacks()
    else:
        _run_single_attack(args.attack)


def _run_single_attack(attack_name: str) -> None:
    if attack_name not in KNOWN_ATTACKS:
        print(f"Unknown attack: {attack_name!r}", file=sys.stderr)
        raise SystemExit(1)

    log.debug(
        "qa_guardrails_entrypoint",
        pii_class=PIIRedactor.__name__,
        limits_class=RunLimits.__name__,
        fallback_model=fallback_config.get_current_model(),
        retry_decorator=with_retry.__name__,
    )

    client = FundingClient()
    invoke_state, run_limits = prepare_langgraph_invoke({"attack_name": attack_name})
    try:
        final_state = invoke_run_attack_graph(client, invoke_state, run_limits)
    except RateLimitExceeded as exc:
        log.error("rate_limit_exceeded", error=str(exc))
        print(f"error: rate limit exceeded: {exc}", file=sys.stderr)
        _agentops_end_trace("BLOCK")
        raise SystemExit(2) from exc
    result = final_state["result"]
    rule = result["rule"]
    status = result["status"]
    reasoning = result["reasoning"]

    print(f"{rule} | {attack_name} | {status} | {json.dumps(reasoning, ensure_ascii=False)}")

    validated = AttackResult.model_validate(result)
    release = _compute_release_recommendation([_adversarial_entry(attack_name, validated)])

    url = _agentops_session_url()
    if url:
        print(f"AgentOps session: {url}")

    _agentops_end_trace(release["decision"])

    raise SystemExit(1 if release["decision"] == "BLOCK" else 0)


def _run_all_attacks() -> None:
    client = FundingClient()
    adversarial: list[dict[str, Any]] = []

    for name in sorted(ATTACKS.keys()):
        fn = ATTACKS[name]
        res = fn(client)
        row = _adversarial_entry(name, res)
        adversarial.append(row)

    report = _build_report(
        api_base_raw=os.environ.get("FUNDING_API_BASE", ""),
        adversarial=adversarial,
    )
    _write_report(report)

    _print_summary_table(adversarial)

    url = _agentops_session_url()
    if url:
        print(f"AgentOps session: {url}")

    decision = report["release_recommendation"]["decision"]
    _agentops_end_trace(decision)

    raise SystemExit(1 if decision == "BLOCK" else 0)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse CLI flags such as --attack duplicate_funding (§13.2)."""
    return _build_arg_parser().parse_args(argv)


if __name__ == "__main__":
    main()
