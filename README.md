# Legal Funding QA Agent

One-sentence description: "An autonomous QA agent that attacks financial and legal invariants in a pre-settlement funding API, produces an auditable JSON report, and feeds a go/no-go signal directly into the CI/CD release pipeline."

---

## Why this exists

Traditional test suites assert what you already expect; this agent attacks what you did not model. In legal-tech fintech, a miscalculated payoff is a regulatory finding, a wrong lien priority is legal liability, and a float in a money field is an audit event. The agent is built to surface those failure modes before production does, with evidence suitable for a release gate, not just a failing assertion.

---

## Architecture

```
Explorer → Adversarial Agent → Judge Agent → Report + Release Gate
                ↑
         Synthetic Data
```

| Component | Role |
|---|---|
| Explorer | Maps API and UI surfaces and seeds scenarios the attacks can reach. |
| Adversarial Agent | Drives edge-case requests and collects raw responses as evidence. |
| Judge Agent | Interprets evidence against invariants and explains verdicts in natural language. |
| Report + Release Gate | Emits `artifacts/report.json` and a BLOCK / WARN / PASS decision for CI/CD. |
| Synthetic Data | Generates valid case, lien, and funding graphs so attacks do not depend on hand-written fixtures alone. |

---

## Repository layout

```
agent/
  clients/
    funding_client.py         # typed httpx wrapper — every call logged
    lien_client.py            # lien management endpoints
    disbursement_client.py    # settlement disbursement endpoints
  models/
    case.py                   # Case, CaseStatus, Jurisdiction
    funding.py                # FundingApplication, FundingContract, Payoff
    lien.py                   # MedicalLien, LienPriority, LienRelease
    disbursement.py           # SettlementDisbursement, WaterfallResult
    money.py                  # Cents type alias, money validators
  explorer/
    explorer.py               # happy-path: apply → approve → disburse → payoff
  ui_explorer/
    browser_agent.py          # Playwright as LLM browser-use tool
    page_models.py            # soft page objects — LLM updates these
    self_heal.py              # selector repair pipeline
    bug_reporter.py           # agent-authored bug reports → artifacts/
  adversary/
    attacks.py                # one function per invariant, returns AttackResult
    invariants.py             # canonical rule list — edit with care
    red_team.py               # adversarial agents for financial edge cases
  swarm/
    coordinator.py            # orchestrates UI + API agents in parallel
    reconciliation.py         # UI-to-API financial reconciliation verifier
  eval/
    judge_agent.py            # grades other agents' outputs
    dspy_optimizer.py         # programmatic prompt optimization pipeline
  synthetic/
    data_factory.py           # base relational data generators
    case_generator.py         # legal case + funding portfolio scenarios
    lien_generator.py         # complex multi-party lien portfolios
  judge/
    judge.py                  # LLM-driven verdict + JSON report emitter
    prompts.py                # judge prompt templates, versioned by hash
  guardrails/
    __init__.py               # create_guarded_agent_state() entry point
    pii_redactor.py           # presidio-based PII detection and redaction
    rate_limiter.py           # per-run model and tool call caps
    retry_policy.py           # scoped retry + fallback model config
  graph.py                    # LangGraph wiring: explorer → swarm → adversary → judge
  main.py                     # CLI entry point
artifacts/                    # run outputs (gitignored)
  happy_path.json
  ui_bugs/                    # agent-authored bug reports
  attacks.json
  report.json
config/
  rate_caps.json              # jurisdiction usury limits — never hardcode
PLAN.md                       # invariants in prose
CONTRIBUTING.md               # contributor guide
DECISIONS.md                  # architecture decision records
```

---

## Domain glossary

| Term | Definition |
|---|---|
| Pre-settlement funding | Non-recourse cash advance to a plaintiff against a pending lawsuit. If the case resolves for $0, the advance is not repaid. |
| Non-recourse | The company's only collateral is lawsuit proceeds — not the plaintiff personally. |
| Medical lien | A healthcare provider's legal claim on settlement proceeds in exchange for deferred-payment treatment. |
| Lien priority | The legal order in which lienholders are paid. Federal liens (Medicare/Medicaid) are super-priority and cannot be subordinated. |
| Attorney acknowledgment | Written confirmation from the plaintiff's attorney they will honor the payoff from settlement proceeds. Required before any disbursement. |
| Settlement waterfall | Ordered disbursement: super-priority liens → medical liens → funding payoff → attorney fees → plaintiff remainder. |
| Payoff amount | Principal + accrued interest + fees. Exact day count from disbursement_date matters — month approximations are a material dollar error. |
| Case max exposure | Maximum the platform will advance against a case, typically a % of estimated settlement value. |
| RAG system | Retrieval-augmented generation — used for surfacing case documents and legal precedents. Hallucination here = bad legal advice. |

---

## Browser agent architecture (Playwright as browser-use)

The browser layer treats Playwright as a perception-action loop for an LLM, not a scripted automation runner. The agent navigates by semantic intent, identifies broken flows, and writes structured bug reports.

### Browser agent architecture (core loop)

```python
# ui_explorer/browser_agent.py
class BrowserAgent:
    """
    LLM-driven Playwright agent. The agent receives a goal, perceives
    the current page state as structured HTML + screenshot, decides
    the next action, and executes it. No fixed script.

    Termination conditions: goal_reached | max_steps | unrecoverable_error
    """
    async def run(self, goal: str) -> BrowserRunResult: ...
    async def _perceive(self, page: Page) -> PageState:
        """Snapshot: accessibility tree + screenshot + URL + title."""
        ...
    async def _decide(self, state: PageState, goal: str) -> BrowserAction:
        """LLM call: given this state and goal, what is the next action?"""
        ...
    async def _act(self, page: Page, action: BrowserAction) -> ActionResult:
        """Execute: click | fill | navigate | assert | report_bug"""
        ...
```

### Self-healing selectors

When the UI changes, `self_heal.py` detects broken selectors, re-queries the LLM for a repaired version, and proposes a PR with the diff. Engineers review — they do not re-author.

### Agent-authored bug reports

When the browser agent identifies a broken flow, it produces a structured bug report — not a test failure:

```json
{
  "bug_id": "UI-0042",
  "discovered_by": "browser_agent",
  "goal": "verify payoff amount displayed on case C-101 matches API",
  "invariant": "INV-13",
  "severity": "CRITICAL",
  "steps_to_reproduce": [
    "Navigate to /cases/C-101/funding",
    "Observe displayed payoff: $12,347.82",
    "API GET /funding/F-0055/payoff returned: 1234750 cents ($12,347.50)"
  ],
  "evidence": {
    "screenshot": "artifacts/ui_bugs/UI-0042.png",
    "api_response": { "total_cents": 1234750 },
    "ui_text_extracted": "$12,347.82"
  },
  "delta_cents": 32,
  "reasoning": "UI displays rounded float; API returns integer cents. Discrepancy of 32 cents. INV-13 breached."
}
```

---

## Prompt optimization (DSPy)

The Judge’s reasoning quality is not left to intuition. Prompts are programmatically optimized against a held-out eval set before any prompt change ships to production.

### Why DSPy instead of hand-tuned prompts

Hand-tuned prompts degrade silently when API response shapes change or new invariants are added. DSPy turns the prompt into a module with a measurable score — regression becomes detectable, not discovered by a live incident.

### Optimization pipeline (high level)

```python
# eval/dspy_optimizer.py
class JudgeModule(dspy.Module):
    """
    Input:  AttackResult evidence dict + invariant description
    Output: Verdict (HELD | BREACHED | INDETERMINATE) + reasoning string
    Optimized against: labeled_verdicts.json (ground truth from human review)
    """
    def forward(self, evidence: dict, invariant_description: str) -> JudgeOutput: ...

class PromptOptimizationPipeline:
    """
    1. Load held-out eval set (never used during optimization)
    2. Run BootstrapFewShot optimizer on training set
    3. Score optimized module against eval set
    4. Only replace production prompt if score >= baseline (enforces INV-20)
    5. Log score delta, old prompt hash, new prompt hash
    """
    def run(self) -> OptimizationResult: ...
```

---

## Red teaming

The `adversary/red_team.py` layer builds agents designed to find financial edge cases a human tester would rarely construct. These are not scripted tests — they are adversarial agents with a goal: produce wrong financial outcomes and collect evidence.

### Hypothesis-based property attacks

For mathematical invariants (INV-04, INV-06, INV-12), hypothesis can generate thousands of input combinations automatically.

---

## Synthetic data generation

The `synthetic/` layer generates complex relational legal funding scenarios to stress-test agent reasoning and retrieval behavior.

### Design principles

- **Relational integrity**: linked cases/fundings/liens/disbursements; no orphaned rows
- **Edge case density**: intentionally produces boundary scenarios (usury caps, zero remainder, priority edges)
- **Deterministic by seed**: a seed reproduces a portfolio across machines and engineers

---

## Swarm architecture

`swarm/coordinator.py` orchestrates specialized agents in parallel: API adversary, browser agent, and reconciliation verifier.

| Layer | Component | Details |
|---|---|---|
| Orchestration | Swarm Coordinator | LangGraph supervisor node — routes tasks, collects results, merges outputs |
| Agent 1 | API Adversary | `attacks.py` · Invariants INV-01 through INV-12 |
| Agent 2 | Browser Agent | `browser_agent.py` · Invariants INV-13 through INV-16 |
| Agent 3 | Reconciliation Verifier | Cross-validates UI state against API state |
| Evaluation | Judge Agent | DSPy-optimized · Scores outputs · Produces final report |

---

## Release gate report schema (full)

`artifacts/report.json` feeds a go/no-go decision into CI/CD. Full schema:

```json
{
  "run_id": "uuid4",
  "started_at": "2026-04-08T08:00:00-06:00",
  "api_base": "redacted",
  "prompt_versions": {
    "waterfall_judge": "sha256:a1b2c3...",
    "ui_reconciliation_judge": "sha256:d4e5f6..."
  },
  "happy_path": {
    "status": "PASS|FAIL",
    "funding_id": "F-0042",
    "steps": [
      {"step": "create_case",             "status": 201, "summary": "case C-101 created, status ACTIVE"},
      {"step": "submit_application",      "status": 201, "summary": "applied for 500000 cents"},
      {"step": "attorney_acknowledgment", "status": 200, "summary": "ack recorded, dated 2026-04-08"},
      {"step": "approve_funding",         "status": 200, "summary": "approved 500000 cents"},
      {"step": "disburse_funds",          "status": 200, "summary": "disbursed, effective 2026-04-08"},
      {"step": "compute_payoff",          "status": 200, "summary": "payoff 537500 cents at day 90"},
      {"step": "record_settlement",       "status": 200, "summary": "waterfall validated"},
      {"step": "void_funding",            "status": 200, "summary": "cleanup complete"}
    ]
  },
  "adversarial": [
    {
      "rule": "INV-01",
      "name": "duplicate_active_funding",
      "severity": "CRITICAL",
      "status": "HELD|BREACHED|INDETERMINATE",
      "evidence": {},
      "reasoning": "Judge's natural-language explanation"
    }
  ],
  "ui_reconciliation": [
    {
      "rule": "INV-13",
      "funding_id": "F-0042",
      "api_payoff_cents": 537500,
      "ui_displayed_cents": 537500,
      "delta_cents": 0,
      "status": "HELD"
    }
  ],
  "eval_layer": [
    {
      "rule": "INV-18",
      "test": "rag_cross_case_leakage",
      "status": "HELD",
      "reasoning": "RAG returned only C-101 documents for C-101 query."
    }
  ],
  "summary": {
    "held": 18,
    "breached": 1,
    "indeterminate": 1,
    "critical_breaches": 0,
    "high_breaches": 1,
    "headline": "One HIGH breach: INV-04 — interest accrues from application_date not disbursement_date"
  },
  "release_recommendation": {
    "decision": "BLOCK|WARN|PASS",
    "reason": "INV-04 HIGH breach requires override ticket before deploy",
    "override_required": true,
    "blocking_rules": ["INV-04"]
  }
}
```

---

## Contributor guide

The full, step-by-step contributor workflow (including the code review checklist) lives in [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Invariants under attack

| ID | Rule | Blast radius |
|---|---|---|
| INV-01 | No duplicate active funding on the same case | Regulatory / duplicate disbursement |
| INV-02 | Funding cannot be approved if case status is settled, dismissed, or closed | Unrecoverable non-recourse loss |
| INV-03 | Attorney acknowledgment must exist and be dated before funds disburse | Legal liability / clawback |
| INV-04 | Payoff = principal_cents + accrued_interest_cents + fees_cents; interest accrues from disbursement_date, not application_date | Direct $ — overcharge or undercharge |
| INV-05 | Approved funding <= case_max_exposure at time of approval | Credit / loss risk |
| INV-06 | Jurisdiction rate cap enforced — interest rate must not exceed applicable state usury limit | Regulatory / void contract |
| INV-07 | Settlement waterfall order: Medicare/Medicaid → medical liens by priority_rank → funding payoff → attorney fees → plaintiff remainder | Legal liability to lienholders |
| INV-08 | Medical lien balance cannot exceed original_billed_amount | Overbilling / provider dispute |
| INV-09 | Plaintiff remainder after waterfall must be >= 0; disbursement must not proceed if obligations exceed settlement | Negative remainder = company debt |
| INV-10 | Cancelled or expired applications release reserved case capacity immediately | Inventory leak / over-exposure |
| INV-11 | All money fields are integer cents — never floats, never strings with >2dp | Audit / regulatory finding |
| INV-12 | Interest uses exact calendar day count from disbursement_date to payoff_date | Off-by-days = material $ error at portfolio scale |

---

## Quick start

```bash
git clone <repository-url>
cd legal-funding-qa-agent
cp .env.example .env
# add keys (e.g. MOVEDOCS_API_BASE=http://localhost:8000 for the mock API)
docker-compose up -d
python verify_bugs.py
python -m agent.main
```

Expected terminal output of step 5:

```
INV-01 | duplicate_funding            | HELD     | "Duplicate correctly rejected."
INV-11 | float_payoff                 | BREACHED | "total_cents returned as float: 523260.0"
INV-04 | interest_from_application_date| BREACHED | "Plaintiff overcharged by 9 days = 431 cents ($4.31)."
INV-07 | waterfall_priority           | BREACHED | "Medicare paid second despite super-priority."

Release gate: BLOCK
```

---

## Demo findings

| Invariant | Finding | Severity | $ Impact |
|---|---|---|---|
| INV-11 | payoff_amount returned as float (523260.0) | CRITICAL | Audit / regulatory |
| INV-04 | Interest accrues from application_date not disbursement_date | HIGH | $4.31 per contract |
| INV-07 | Medicare lien paid after MEDICAL lien despite super-priority | HIGH | Legal liability |

---

## Stack

| Core | Agents & ops |
|---|---|
| Python 3.11, httpx, pydantic v2, hypothesis | LangGraph, langchain-anthropic, structlog, AgentOps |

---

## Design decisions

- Why LangGraph instead of pytest? The agent needs to reason, not just assert — when a payoff is off, the question is why (day count, rate, fee), and a Judge LLM explains that where pytest would only show a failure.
- Why Playwright as browser-use instead of scripted selectors? The UI changes, scripted selectors break silently, and navigating by semantic intent degrades gracefully and surfaces flows no one scripted.
- Why DSPy instead of hand-tuned prompts? Prompts degrade silently when response shapes change, and DSPy turns the Judge into a module with a measurable eval score so regression is detectable in a regulated financial domain.
- Why integer cents throughout? Floating-point in payoff math is a compliance finding, not a rounding error, and integer arithmetic is exact — there is no acceptable alternative in legal funding.

---

## CLAUDE.md

Every AI agent working in this repo is bound by [CLAUDE.md](CLAUDE.md) — a contract that defines invariants, forbidden patterns, contributor standards, and escalation rules.

## License & Attribution
MIT License — Copyright 2026 Brian Padgett

This framework was independently developed prior to any employment engagement.
All code, architecture decisions, and documentation represent original work
authored and committed by Brian Padgett. Commit history and timestamps are
the authoritative record of authorship.