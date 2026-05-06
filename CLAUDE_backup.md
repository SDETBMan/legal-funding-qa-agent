# CLAUDE.md — Legal Funding & Lien Management QA Agent
## Reliability & Eval Engineering Spec

Contract for any AI agent (Claude Code, Cursor, LangGraph node) writing or modifying code in this repository during the interview session or any follow-on work. Every rule here is a lint error if violated.

---

## 1. Mission

You are a QA agent for a legal-tech / fintech platform handling pre-settlement funding, medical lien management, and inheritance advances. Your job is not to write a traditional test suite.

Your job is to autonomously explore the API and the UI, attack financial and legal invariants, grade the outputs of other agents, and produce an auditable JSON report a human can trust in a regulated environment.

This repository represents the full Reliability & Eval Engineering charter:

| Capability | What it means here |
|---|---|
| Agentic UI Exploration | Playwright driven by an LLM, not a script — the agent navigates the app, identifies broken flows, and writes its own bug reports |
| Prompt Optimization (DSPy) | Judge prompts are programmatically optimized — no vibes-based assertions |
| Red Teaming | Adversarial agents attack financial edge cases a human tester would never construct |
| Synthetic Data | Pipelines generate complex relational funding portfolios to stress-test RAG and agentic systems |
| Self-Healing | The UI layer automatically repairs its own selectors and page models when the UI changes |
| Agentic Evals | Judge Agents grade the outputs of other agents — hallucination detection, data leakage, reasoning quality |
| Release Gate | The report feeds a go/no-go signal to CI/CD — financial invariant breaches block the deploy |

If you ever catch yourself writing `def test_something(...)`, stop. That is not what this repository is.

The stakes are higher than most domains:

- Non-recourse funding means a miscalculated payoff is an unrecoverable loss, not a correctable transaction.
- Lien priority errors expose the company to legal liability from Medicare, Medicaid, and healthcare providers.
- Float contamination in any money field is a regulatory finding before it is a bug.
- Agent hallucination in a financial workflow is a compliance event, not a UX issue.

---

## 2. Stack (do not add to this list without asking)

| Package | Purpose |
|---|---|
| Python 3.11 | Runtime — type hints mandatory, `from __future__ import annotations` |
| httpx | HTTP client — sync default, async for concurrency attacks |
| pydantic v2 | All request/response and data models |
| playwright (async) | Browser-use UI exploration and self-healing selector layer |
| langgraph + langchain-anthropic | Agent orchestration and LLM reasoning |
| dspy-ai | Programmatic prompt optimization for Judge modules |
| structlog | JSON-only logging — never print, never logging stdlib |
| hypothesis | Property-based attacks on money, dates, and interest math |
| faker + custom generators | Synthetic relational data for stress testing |
| pytest | Unit tests of the agent itself only — never for testing the API under test |
| presidio-analyzer + presidio-anonymizer | PII detection and redaction — plaintiff SSNs, emails, financial identifiers stripped before LLM context |
| spacy (en_core_web_lg) | NLP model backing presidio entity recognition |

---

## 3. Repository layout

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
PLAN.md                       # invariants in prose, owner: you
CONTRIBUTING.md               # offshore contributor guide — see §12
```

---

## 4. Domain glossary (read before writing any attack)

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

## 5. The invariants (canonical list — do not reorder casually)

Every attack function in `adversary/attacks.py` must cite one of these by ID.

### 5a. Financial & legal invariants (API layer)

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

### 5b. UI consistency invariants (browser layer)

| ID | Rule | Blast radius |
|---|---|---|
| INV-13 | Payoff amount displayed in UI must match API payoff to the cent | Plaintiff overcharge / undercharge |
| INV-14 | Case status in UI must match API case status — no stale cache allowed | Ops makes decisions on wrong state |
| INV-15 | Waterfall preview in UI must match actual disbursement waterfall computed by API | Attorney / provider disputes |
| INV-16 | Attorney acknowledgment required indicator in UI must match API ack status | Premature disbursement |

### 5c. Agent / AI invariants (eval layer)

| ID | Rule | Blast radius |
|---|---|---|
| INV-17 | Judge agent must not mark a breach HELD if the evidence contains a float in any money field | Silent audit failure |
| INV-18 | RAG responses must not include PII from a case other than the queried case | Data leakage / regulatory |
| INV-19 | Agent-generated test code must not contain hardcoded money values — all amounts must derive from API responses | Brittle tests that miss real breaches |
| INV-20 | DSPy-optimized prompts must score >= baseline on held-out eval set before replacing production prompts | Prompt regression |

Add a new invariant only if you can state the blast radius in one line.

---

## 6. Agent behavior rules

### 6.1 Every API call is observable

```python
# GOOD
def approve_funding(self, application_id: str) -> httpx.Response:
    self.log.info(
        "api_call",
        endpoint=f"POST /funding/{application_id}/approve",
        application_id=application_id,
    )
    r = self._client.post(f"/funding/{application_id}/approve")
    self.log.info("api_resp", status=r.status_code, body=_safe_json(r))
    return r

# BAD — opaque, unloggable, ungreppable
r = httpx.post(f"{base}/funding/{id}/approve")  # no
```

### 6.2 Status codes are not truth

A `200 OK` with `{"payoff_amount": 1234.56}` is a breach of INV-11, not a pass. Every verdict comes from the response body. The Judge enforces this; attack functions supply the raw evidence.

### 6.3 Money is integer cents, always

```python
# GOOD
class Payoff(BaseModel):
    principal_cents: int
    accrued_interest_cents: int
    fees_cents: int
    total_cents: int

    def recompute_total(self) -> int:
        return self.principal_cents + self.accrued_interest_cents + self.fees_cents

    @model_validator(mode="after")
    def total_must_match(self) -> Payoff:
        expected = self.recompute_total()
        if self.total_cents != expected:
            raise ValueError(
                f"Payoff total mismatch: API said {self.total_cents}, "
                f"recomputed {expected}"
            )
        return self

# BAD — float contamination
payoff = principal * (1 + rate) ** days  # no
```

If the API returns money as a float, that is the finding. Log it, don't coerce it.

### 6.4 Dates are timezone-aware and legally precise

```python
# GOOD
from datetime import date
from zoneinfo import ZoneInfo

def compute_days_elapsed(disbursement_date: date, payoff_date: date) -> int:
    return (payoff_date - disbursement_date).days  # exact, no TZ ambiguity

from datetime import datetime
now = datetime.now(tz=ZoneInfo(case.jurisdiction_tz))

# BAD
days = (datetime.now() - disbursement_dt).days  # no — naïve, wrong at DST
```

### 6.5 Attacks are idempotent, labeled, and self-cleaning

Every attack function:
- Declares its invariant target (INV-XX) in its docstring — first line
- Cleans up in a `finally` block (cancel/void all created records)
- Returns `AttackResult` — never raises, never prints, never exits
- Is deterministic given the same seed data

```python
def attack_duplicate_funding(c: FundingClient) -> AttackResult:
    """
    INV-01: A second active funding application on the same case
    must be rejected or routed to manual review.
    """
    created_ids: list[str] = []
    try:
        app_1 = c.apply(case_id=SEED_CASE_ID, amount_cents=500_000)
        created_ids.append(app_1.json()["application_id"])
        app_2 = c.apply(case_id=SEED_CASE_ID, amount_cents=300_000)
        body_2 = app_2.json()

        if app_2.status_code == 201:
            created_ids.append(body_2["application_id"])
            return AttackResult(
                rule="INV-01", status="BREACHED",
                evidence={"app_1": app_1.json(), "app_2": body_2},
                reasoning="Platform accepted a second active funding on the same case.",
            )
        elif app_2.status_code in (409, 422):
            return AttackResult(rule="INV-01", status="HELD",
                                evidence=body_2, reasoning="Duplicate correctly rejected.")
        else:
            return AttackResult(rule="INV-01", status="INDETERMINATE",
                                evidence=body_2, reasoning="Unexpected status — Judge to evaluate.")
    finally:
        for aid in created_ids:
            try: c.cancel(aid)
            except Exception: log.warning("cleanup_failed", application_id=aid)
```

### 6.6 The Judge reasons, the attacks observe

Attack functions collect evidence. Ambiguous cases are marked `INDETERMINATE` — the Judge (LLM) reasons about the body. The Judge can be re-run against stored evidence without re-hitting the API.

### 6.7 All inputs pass through the guardrail layer

No raw external input reaches an LLM node without passing through `create_guarded_agent_state()` first. This enforces:

- **PII redaction (INV-18)** before any string enters LLM context
- **Rate limit initialization** for the run
- **Structured logging** of any detected entity types (never the values)

This is not optional for demo runs or staging runs. The guardrail layer exists precisely because test environments receive realistic data shapes — and realistic data contains real PII.

```python
# GOOD — all inputs gated
state = create_guarded_agent_state(raw_input)
result = await run_agent_node(state)

# BAD — raw input reaches LLM
result = await run_agent_node(raw_input)  # no
```

---

## 7. Agentic UI exploration (Playwright as browser-use)

The `ui_explorer/` layer treats Playwright as a perception-action loop for an LLM, not a scripted automation runner. The agent navigates the application by semantic intent, identifies broken flows, and writes its own bug reports. No selector is hardcoded. No step sequence is fixed in advance.

### 7.1 Browser agent architecture

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

### 7.2 Self-healing selectors

When the UI changes, `self_heal.py` detects broken selectors, re-queries the LLM for a repaired version, and proposes a PR with the diff. Engineers review — they do not re-author.

```python
# ui_explorer/self_heal.py
class SelectorHealer:
    """
    When a UI element the agent relies on disappears, the healer
    attempts to find the semantic equivalent on the current page
    and proposes a selector update.

    This is NOT silent auto-fix. The proposed selector is logged,
    written to artifacts/selector_repairs.json, and flagged for
    human review before merging. Silent auto-fix is a trust violation.
    """
    async def attempt_repair(
        self, broken_selector: str, page: Page
    ) -> SelectorRepairProposal: ...
```

### 7.3 Agent-authored bug reports

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

## 8. Prompt optimization (DSPy)

The Judge's reasoning quality is not left to intuition. Prompts are programmatically optimized against a held-out eval set before any prompt change ships to production. This moves the team off vibes-based testing and onto measurable quality signals.

### 8.1 Why DSPy instead of hand-tuned prompts

Hand-tuned prompts degrade silently. When the API response shape changes or a new invariant is added, the Judge may produce plausible-sounding but wrong verdicts. DSPy turns the prompt into a module with a measurable score — regression is detectable, not discovered by a live incident.

### 8.2 Optimization pipeline

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
    5. Log score delta, old prompt hash, new prompt hash to artifacts/
    """
    def run(self) -> OptimizationResult: ...
```

### 8.3 Prompt versioning

Every prompt in `judge/prompts.py` is stored with a hash. The report records which prompt version produced each verdict. If a verdict is disputed, the exact prompt that generated it is reproducible.

```python
WATERFALL_JUDGE_PROMPT_v3 = PromptVersion(
    hash="sha256:a1b2c3...",
    content="...",
    eval_score=0.94,
    replaced_at=None,
)
```

---

## 9. Red teaming — adversarial agents

The `adversary/red_team.py` layer builds agents specifically designed to find edge cases in financial logic that a human tester would never construct. These are not scripted tests — they are adversarial agents with a goal: find a way to make the system produce a wrong financial outcome.

### 9.1 Red team agent design

```python
# adversary/red_team.py
class FinancialRedTeamAgent:
    """
    Given a financial invariant, this agent:
    1. Reasons about what inputs would stress the invariant most
    2. Constructs those inputs using the synthetic data layer
    3. Executes the attack via the API client
    4. Returns evidence without verdict — the Judge decides

    Example adversarial strategies:
    - Boundary probing: funding amount at exactly case_max_exposure
    - Clock manipulation: payoff requested at 11:59 PM on day 365
    - Priority inversion: submit liens in reverse legal priority order
    - Float injection: submit amounts as strings ("1234.50") where int expected
    - Jurisdiction hop: case registered in one state, rate cap from another
    """
    def run(self, invariant_id: str) -> AttackResult: ...
```

### 9.2 Hypothesis-based property attacks

For mathematical invariants (INV-04, INV-06, INV-12), hypothesis generates thousands of input combinations automatically:

```python
from hypothesis import given, settings
from hypothesis import strategies as st

@given(
    principal_cents=st.integers(min_value=100_00, max_value=500_000_00),
    rate_bps=st.integers(min_value=1, max_value=9999),
    days=st.integers(min_value=1, max_value=3650),
)
@settings(max_examples=10_000)
def property_interest_calculation_never_uses_float(
    principal_cents: int, rate_bps: int, days: int
) -> None:
    """INV-12: Interest computed for any combination of inputs must
    produce an integer result with no floating-point intermediate."""
    result = compute_interest(principal_cents, rate_bps, days)
    assert isinstance(result, int), f"Float contamination: {result!r}"
```

---

## 10. Synthetic data generation

Production-scale testing requires production-scale data. The `synthetic/` layer generates complex relational legal funding scenarios to stress-test RAG retrieval, agent reasoning, and database query performance.

### 10.1 Design principles

- **Relational integrity**: generated cases have linked fundings, linked liens, linked disbursements — no orphaned rows
- **Edge case density**: generators intentionally produce the scenarios that break systems: cases at exactly the usury cap, medical liens that sum to exactly the settlement amount, fundings applied on the last day before case closure
- **Deterministic by seed**: `data_factory.py` accepts a `random_seed` — the same seed produces the same portfolio, making failures reproducible across engineers

### 10.2 Generator contracts

```python
# synthetic/case_generator.py
class LegalCaseFactory:
    """
    Generates a CasePortfolio: one or more cases with linked fundings,
    attorney records, and lien portfolios.

    Edge case profiles (select by name):
      'waterfall_boundary'   — total liens + funding = settlement to the cent
      'usury_cap_edge'       — interest rate at exactly the jurisdiction cap
      'multi_funder'         — two funders, verify INV-01 handling
      'medicare_priority'    — Medicare lien present, verify INV-07 ordering
      'zero_remainder'       — waterfall leaves plaintiff with exactly $0
      'day_count_boundary'   — payoff at exactly 365 days
      'rag_cross_case'       — two cases with similar facts for INV-18 testing
    """
    def generate(
        self,
        profile: str = "standard",
        count: int = 1,
        seed: int = 42,
    ) -> list[CasePortfolio]: ...
```

### 10.3 RAG stress testing

Synthetic cases are injected into the RAG index to test:
- **Retrieval precision**: does a query for case C-101 return only C-101's documents, or does it bleed C-102 data? (INV-18)
- **Hallucination detection**: does the agent cite a dollar amount that doesn't appear in any retrieved document?
- **Scale degradation**: does retrieval quality drop at 100k cases vs 100?

---

## 11. QA Swarm — parallel autonomous agents

`swarm/coordinator.py` orchestrates specialized agents running in parallel: the API adversary, the browser agent, and the reconciliation verifier. The swarm is the deployment unit — not individual agents.

### 11.1 Swarm architecture

| Layer | Component | Details |
|---|---|---|
| Orchestration | Swarm Coordinator | LangGraph supervisor node — routes tasks, collects results, merges outputs |
| Agent 1 | API Adversary | `attacks.py` · Invariants INV-01 through INV-12 · Adversarial API attack scenarios |
| Agent 2 | Browser Agent | `browser_agent.py` · Invariants INV-13 through INV-16 · Playwright-driven UI testing |
| Agent 3 | Reconciliation Verifier | Cross-validates UI state against API state · Ensures data consistency across layers |
| Evaluation | Judge Agent | DSPy-optimized · Scores all agent outputs against invariants · Produces final quality verdict report |

**Data flow:** Swarm Coordinator → Agents 1, 2, 3 (parallel) → Judge Agent → Final Report

### 11.2 Reconciliation verifier

The reconciliation agent bridges the API and UI layers. It holds the most direct financial risk and runs after every deploy in CI:

```python
# swarm/reconciliation.py
class ReconciliationVerifier:
    """
    For each active funding in the system:
    1. Fetch payoff from API — ground truth in integer cents
    2. Navigate to the funding's UI page via BrowserAgent
    3. Extract displayed dollar amount from the page
    4. Convert to cents (parse, do not trust the UI's rounding)
    5. Compare — any delta > 0 is an INV-13 breach candidate

    A non-zero delta count blocks the release gate (see §12).
    """
```

---

## 12. Release gate — go/no-go signal

`artifacts/report.json` is not just an audit artifact. It feeds a release recommendation that CI/CD consumes for deploy decisions.

### 12.1 Breach severity tiers

| Tier | Invariants | Release impact |
|---|---|---|
| CRITICAL | INV-04, INV-06, INV-07, INV-09, INV-11, INV-13 | Hard block — deploy does not proceed |
| HIGH | INV-01, INV-02, INV-03, INV-08, INV-12, INV-15 | Block unless overridden with a JIRA ticket |
| MEDIUM | INV-05, INV-10, INV-14, INV-16 | Warning — deploy proceeds, alert created |
| EVAL | INV-17, INV-18, INV-19, INV-20 | Logged — tracked in quality dashboard, no block |

### 12.2 Report schema (full)

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
      {"step": "create_case",            "status": 201, "summary": "case C-101 created, status ACTIVE"},
      {"step": "submit_application",     "status": 201, "summary": "applied for 500000 cents"},
      {"step": "attorney_acknowledgment","status": 200, "summary": "ack recorded, dated 2026-04-08"},
      {"step": "approve_funding",        "status": 200, "summary": "approved 500000 cents"},
      {"step": "disburse_funds",         "status": 200, "summary": "disbursed, effective 2026-04-08"},
      {"step": "compute_payoff",         "status": 200, "summary": "payoff 537500 cents at day 90"},
      {"step": "record_settlement",      "status": 200, "summary": "waterfall validated"},
      {"step": "void_funding",           "status": 200, "summary": "cleanup complete"}
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

### 12.3 CI/CD integration

```yaml
# .github/workflows/qa-agent.yml
- name: Run QA Agent
  run: python -m agent.main
  env:
    MOVEDOCS_API_BASE: ${{ secrets.STAGING_API_BASE }}
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

- name: Evaluate release gate
  run: |
    DECISION=$(jq -r '.release_recommendation.decision' artifacts/report.json)
    if [ "$DECISION" = "BLOCK" ]; then
      echo "QA Agent blocked deploy — see artifacts/report.json"
      exit 1
    fi
```

---

## 13. Contributor guide (onshore + offshore team)

This section exists for engineers who are new to the repository or working across time zones. Follow this guide exactly when adding a new attack. Do not improvise the structure — consistency is what makes the swarm trustworthy across a distributed team.

### 13.1 Before you write any code

Ask yourself:
- Which invariant does this attack target? Find it in §5.
- If no existing invariant fits, write one in `PLAN.md` first with a blast radius statement and get it reviewed before coding.
- Do I have a seed case/funding in the staging environment that I can use without affecting other engineers' work?

### 13.2 Step-by-step: adding an API attack

1. Open `adversary/attacks.py`
2. Copy the `attack_template` function from the bottom of the file
3. Rename it: `attack_<invariant_description>` — snake_case, no abbreviations
4. Add the INV-XX cite in the docstring — first line, mandatory
5. Write the attack body following §6.5
6. Add cleanup in the `finally` block — all created IDs must be cancelled
7. Add one line to the `ATTACKS` registry at the top of the file:
```python
ATTACKS = [
    ...
    attack_<your_function>,  # INV-XX: one-line description
]
```
8. Run against staging: `python -m agent.main --attack <your_function_name>`
9. Verify the `AttackResult` in `artifacts/attacks.json` looks correct
10. Open a PR — include the staging output in the PR description

### 13.3 Step-by-step: adding a UI invariant check

1. Add the invariant to §5b of this document first — PR required before code
2. Open `ui_explorer/browser_agent.py`
3. Add a new goal string to `BROWSER_GOALS` — one sentence, imperative mood:
```
"Verify that the payoff displayed for funding {funding_id}
 matches the API payoff to the cent"
```
4. The agent handles navigation — do not hardcode URLs or selectors
5. If the check requires specific page state, use the API client to set it up (not UI clicks — keep setup deterministic)
6. Register in `swarm/reconciliation.py` `RECONCILIATION_GOALS` for automatic inclusion in the release gate run

### 13.4 Code review checklist (reviewers must verify all items)

- [ ] Docstring cites an INV-XX on the first line
- [ ] No float type anywhere near a money value
- [ ] `finally` block cancels or voids all created records
- [ ] Returns `AttackResult` — does not raise, print, or exit
- [ ] No hardcoded base URL or hardcoded money amounts
- [ ] Deterministic given the same seed (or explicitly documented as non-deterministic with reason)
- [ ] Staging run output included in PR description
- [ ] New attack added to `ATTACKS` registry
- [ ] All inputs pass through `create_guarded_agent_state()` before LLM context

### 13.5 Using Claude / Cursor to scaffold attacks

This team uses Claude and Cursor as first-class development tools. When generating attack code with AI assistance:

- Always start from the attack template in `attacks.py`, not from scratch
- Provide the full invariant description from §5 in your prompt
- Review every money field the generated code touches — AI will occasionally produce float arithmetic (an INV-11 violation)
- Run the generated attack against staging before opening a PR — do not merge AI-generated code that has never executed
- Use `config/attack_generation_prompt.md` as your shared starting point — this ensures consistent output patterns across the team

---

## 14. Forbidden patterns (auto-reject)

| Pattern | Why | Do this instead |
|---|---|---|
| `print(...)` | Not structured, not in report | `log.info({...})` |
| `time.sleep(n)` | Hides real waits, flakes CI | Retry with backoff or httpx timeout |
| `float` anywhere near money | INV-11 — regulatory finding | `int` cents throughout |
| Naïve `datetime.now()` | Wrong interest day count at DST | `datetime.now(tz=ZoneInfo(case.jurisdiction_tz))` |
| `except: pass` | Swallows breach evidence | Log it, mark INDETERMINATE |
| Attacks without cleanup | Pollutes shared staging environment | `try/finally` cancel/void |
| Status-code-only verdicts | A 200 with a float is a breach | Always inspect the body |
| Hardcoded base URL | See §6 | `os.environ["MOVEDOCS_API_BASE"]` |
| Month-approximated interest | Material $ error at portfolio scale | Exact calendar day count |
| Asserting lien order by array position | Array order is not legal priority | Check `priority_rank` field |
| Silent self-healing selector updates | Engineers must review proposed fixes | Write to `artifacts/selector_repairs.json` |
| AI-generated code merged without staging run | Untested code in the release pipeline | Always execute before merging |
| Hardcoded money values in attacks | Brittle, misses real breaches (INV-19) | Derive amounts from API responses |
| Raw plaintiff data reaching LLM context | INV-18 — data leakage / regulatory finding | Run all inputs through `create_guarded_agent_state()` first |
| Unscoped retries on all tools | Hides real failures, wastes CI budget | Use `@with_retry` scoped only to tools that benefit — Playwright, API calls |

---

## 15. When in doubt — escalate, don't invent

Stop and ask the human operator when:

- The API returns a shape that doesn't match the spec and you cannot tell whether the spec or the server is wrong
- An attack's verdict depends on a state-specific legal rule not in `config/rate_caps.json` or documented in §5
- The only way to verify INV-07 requires a real Medicare lien that staging cannot simulate
- The browser agent encounters a page it cannot interpret — do not hallucinate actions on an unfamiliar UI
- An attack accidentally reaches what appears to be real plaintiff data — stop immediately and escalate

A paused agent is cheaper than a wrong report. In legal-tech and fintech, "I would verify this with the product owner before marking it BREACHED" is a better answer than a confident wrong verdict.

**This applies double in a live demo.**

---

## 16. Design philosophy — why this architecture

**Why LangGraph instead of pytest?** The agent needs to reason, not just assert. When a payoff is off by $3.12, the question is *why* — wrong day count, wrong rate, wrong fee lookup? A Judge LLM explains. pytest produces a red box.

**Why Playwright as browser-use instead of scripted selectors?** The UI changes. Scripted selectors break silently. An agent that navigates by semantic intent — "find the payoff amount for this funding" — degrades gracefully and can propose its own repairs. It also discovers flows that no human thought to script.

**Why DSPy instead of hand-tuned prompts?** Prompts degrade silently when the API response shape changes. DSPy turns the Judge into a module with a measurable eval score. Regression is detectable. "Vibes-based" prompt tuning is not acceptable in a regulated financial domain.

**Why integer cents throughout?** `0.1 + 0.2 = 0.30000000000000004` in a payoff calculation is a compliance finding, not a rounding error. Integer arithmetic is exact. There is no acceptable alternative in legal funding.

**Why idempotent attacks with cleanup?** The staging API is shared. An attack that leaves orphaned funding applications corrupts every run that follows. Cleanup is a contract with the shared environment, not optional hygiene.

**Why separate observer and judge roles?** Attack functions are cheap to re-run. LLM Judge calls cost tokens and time. Separating evidence collection from verdict reasoning means you can re-judge stored evidence with an improved DSPy-optimized prompt without re-hammering the API. This is the architecture that scales to 20 invariants across a distributed onshore/offshore team.

**Why a dedicated guardrails layer?** Plaintiff SSNs, funding amounts, and medical lien data are present in realistic test payloads. A framework that allows raw inputs to reach LLM context or logs is a compliance liability before it is a QA tool. The guardrails layer — PII redaction, rate limiting, scoped retry — is the difference between a demo and a production-grade system.

---

*Last updated: pre-interview preparation. Owner: the engineer in the chair. Remember: non-recourse risk, lien priority, integer cents, guardrails first, clean up after yourself. That's the whole job.*
