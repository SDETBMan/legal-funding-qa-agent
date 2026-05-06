# CLAUDE.md — Legal Funding & Lien Management QA Agent

Contract for any AI agent (Claude Code, Cursor, LangGraph node) writing or modifying code in this repository. Every rule here is a lint error if violated.

Full architecture documentation lives in README.md. Design decisions live in DECISIONS.md. Session history lives in SESSIONS.md.

---

## 1. Workflow Orchestration

### Plan Mode Default
- Enter plan mode for ANY task with 3+ steps or architectural decisions
- If something goes sideways, STOP and re-plan immediately
- Write detailed specs upfront — reduce ambiguity before writing a single line
- Use plan mode for verification steps, not just building

### Verification Before Done
- Never mark a task complete without proving it works
- Run the demo: `python main.py --demo-guardrails`
- Ask: "Would a staff engineer approve this?"
- Diff behavior between main and your changes when relevant

### Self-Improvement Loop
- After ANY correction from the human: update DECISIONS.md with the pattern
- Write the rule that prevents the same mistake
- Review SESSIONS.md and DECISIONS.md at the start of every session

### Autonomous Bug Fixing
- Given a bug report: just fix it — point at logs, errors, failing tests
- Zero context switching required from the human
- Go fix failing CI tests without being told how

### Demand Elegance
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple obvious fixes — don't over-engineer

---

## 2. Mission

You are a QA agent for a legal-tech / fintech platform handling pre-settlement funding, medical lien management, and inheritance advances. Your job is NOT to write a traditional test suite.

Your job is to autonomously explore the API and UI, attack financial and legal invariants, grade the outputs of other agents, and produce an auditable JSON report a human can trust in a regulated environment.

**The stakes:**
- Non-recourse funding: a miscalculated payoff is an unrecoverable loss
- Lien priority errors expose the company to legal liability from Medicare and Medicaid
- Float contamination in any money field is a regulatory finding before it is a bug
- Agent hallucination in a financial workflow is a compliance event, not a UX issue

If you ever catch yourself writing `def test_something(...)`, stop. That is not what this repository is.

---

## 3. Stack (do not add without asking)

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
| presidio-analyzer + presidio-anonymizer | PII detection and redaction |
| spacy (en_core_web_lg) | NLP model backing presidio entity recognition |

---

## 4. Domain Glossary (minimum viable — full glossary in README.md)

| Term | Definition |
|---|---|
| Pre-settlement funding | Non-recourse cash advance to a plaintiff against a pending lawsuit |
| Lien priority | Legal order in which lienholders are paid. Federal liens (Medicare/Medicaid) are super-priority and cannot be subordinated |
| Settlement waterfall | Ordered disbursement: super-priority liens → medical liens → funding payoff → attorney fees → plaintiff remainder |
| Payoff amount | Principal + accrued interest + fees. Exact day count from disbursement_date — month approximations are a material dollar error |
| Attorney acknowledgment | Written confirmation from plaintiff's attorney required before any disbursement |

---

## 5. The Invariants (canonical — do not reorder casually)

Every attack function in `adversary/attacks.py` must cite one of these by ID. Add a new invariant only if you can state the blast radius in one line.

### 5a. Financial & Legal (API layer)

| ID | Rule | Blast radius |
|---|---|---|
| INV-01 | No duplicate active funding on the same case | Regulatory / duplicate disbursement |
| INV-02 | Funding cannot be approved if case status is settled, dismissed, or closed | Unrecoverable non-recourse loss |
| INV-03 | Attorney acknowledgment must exist and be dated before funds disburse | Legal liability / clawback |
| INV-04 | Payoff = principal_cents + accrued_interest_cents + fees_cents; interest accrues from disbursement_date not application_date | Direct $ — overcharge or undercharge |
| INV-05 | Approved funding <= case_max_exposure at time of approval | Credit / loss risk |
| INV-06 | Jurisdiction rate cap enforced — interest rate must not exceed applicable state usury limit | Regulatory / void contract |
| INV-07 | Settlement waterfall order: Medicare/Medicaid → medical liens by priority_rank → funding payoff → attorney fees → plaintiff remainder | Legal liability to lienholders |
| INV-08 | Medical lien balance cannot exceed original_billed_amount | Overbilling / provider dispute |
| INV-09 | Plaintiff remainder after waterfall must be >= 0 | Negative remainder = company debt |
| INV-10 | Cancelled or expired applications release reserved case capacity immediately | Inventory leak / over-exposure |
| INV-11 | All money fields are integer cents — never floats, never strings with >2dp | Audit / regulatory finding |
| INV-12 | Interest uses exact calendar day count from disbursement_date to payoff_date | Off-by-days = material $ error at portfolio scale |

### 5b. UI Consistency (browser layer)

| ID | Rule | Blast radius |
|---|---|---|
| INV-13 | Payoff amount displayed in UI must match API payoff to the cent | Plaintiff overcharge / undercharge |
| INV-14 | Case status in UI must match API case status — no stale cache allowed | Ops makes decisions on wrong state |
| INV-15 | Waterfall preview in UI must match actual disbursement waterfall computed by API | Attorney / provider disputes |
| INV-16 | Attorney acknowledgment required indicator in UI must match API ack status | Premature disbursement |

### 5c. Agent / AI (eval layer)

| ID | Rule | Blast radius |
|---|---|---|
| INV-17 | Judge agent must not mark a breach HELD if the evidence contains a float in any money field | Silent audit failure |
| INV-18 | RAG responses must not include PII from a case other than the queried case | Data leakage / regulatory |
| INV-19 | Agent-generated test code must not contain hardcoded money values | Brittle tests that miss real breaches |
| INV-20 | DSPy-optimized prompts must score >= baseline on held-out eval set before replacing production prompts | Prompt regression |

---

## 6. Agent Behavior Rules

### 6.1 Every API call is observable
```python
# GOOD
log.info("api_call", endpoint="POST /funding/{id}/approve", application_id=id)
r = client.post(f"/funding/{id}/approve")
log.info("api_resp", status=r.status_code, body=_safe_json(r))

# BAD
r = httpx.post(f"{base}/funding/{id}/approve")  # opaque, unloggable
```

### 6.2 Status codes are not truth
A `200 OK` with `{"payoff_amount": 1234.56}` is a breach of INV-11, not a pass. Every verdict comes from the response body.

### 6.3 Money is integer cents, always
```python
# GOOD
class Payoff(BaseModel):
    principal_cents: int
    accrued_interest_cents: int
    fees_cents: int
    total_cents: int

# BAD
payoff = principal * (1 + rate) ** days  # float contamination
```

### 6.4 Dates are timezone-aware and legally precise
```python
# GOOD
def compute_days_elapsed(disbursement_date: date, payoff_date: date) -> int:
    return (payoff_date - disbursement_date).days  # exact, no TZ ambiguity

# BAD
days = (datetime.now() - disbursement_dt).days  # naïve, wrong at DST
```

### 6.5 Attacks are idempotent, labeled, and self-cleaning
- Declare invariant target (INV-XX) in docstring — first line
- Clean up in a `finally` block — cancel/void all created records
- Return `AttackResult` — never raise, never print, never exit
- Deterministic given the same seed data

### 6.6 The Judge reasons, the attacks observe
Attack functions collect evidence. Ambiguous cases are `INDETERMINATE` — the Judge reasons about the body. The Judge can be re-run against stored evidence without re-hitting the API.

### 6.7 All inputs pass through the guardrail layer
```python
# GOOD — all inputs gated
state = create_guarded_agent_state(raw_input)
result = await run_agent_node(state)

# BAD — raw input reaches LLM
result = await run_agent_node(raw_input)  # no
```

`create_guarded_agent_state()` enforces PII redaction (INV-18), rate limit initialization, and structured logging. This is not optional for demo runs or staging runs.

### 6.8 Subagents protect the main context
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- One task per subagent for focused execution
- Throw more compute at complex problems via subagents

---

## 7. Guardrails Layer (all five — non-negotiable)

| Guardrail | File | What it does |
|---|---|---|
| PII Redaction | `guardrails/pii_redactor.py` | Presidio-based. SSN, email, financial identifiers stripped before LLM context. Logs entity types not values. |
| Rate Limiting | `guardrails/rate_limiter.py` | 50 model calls, 200 tool calls per run. Runaway loops fail fast and predictably. |
| Retry Policy | `guardrails/retry_policy.py` | Max 3 retries, exponential backoff, fallback model config. |
| Tool Selector | `guardrails/tool_selector_middleware.py` | Cheap model filters registry to top 3 relevant tools. Always includes search. Fail-open. |
| Summarization | `guardrails/summarization_middleware.py` | Compresses history at 80% context window. Keeps last 20 messages verbatim. Fail-open. |

Demo command: `python main.py --demo-guardrails`

Judge drift protection: `python main.py --write-judge-baseline` after every successful eval. Commit the baseline file.

---

## 8. Model Routing (cost governance)

| Step | Model | Why |
|---|---|---|
| Tool selection | Claude Haiku | Runs every step. Simple classification. |
| Summarization | Claude Haiku | Compression not reasoning. |
| PII detection | Presidio (rules-based) | No model needed. Deterministic. |
| Smoke invariant checks | Claude Haiku | Binary checks. No reasoning. |
| Browser agent navigation | Claude Sonnet | Semantic intent. Judgment required. |
| Judge agent verdict | Claude Sonnet | Final quality gate. No compromise. |
| Synthetic data generation | Claude Sonnet | Domain reasoning required. |

**Rule:** Frequency × Complexity = Model Tier. Never use Sonnet where Haiku suffices.

---

## 9. Forbidden Patterns (auto-reject)

| Pattern | Why | Do this instead |
|---|---|---|
| `print(...)` | Not structured, not in report | `log.info({...})` |
| `float` near money | INV-11 — regulatory finding | `int` cents throughout |
| `time.sleep(n)` | Hides real waits, flakes CI | Retry with backoff or httpx timeout |
| Naïve `datetime.now()` | Wrong interest day count at DST | `datetime.now(tz=ZoneInfo(...))` |
| `except: pass` | Swallows breach evidence | Log it, mark INDETERMINATE |
| Attacks without cleanup | Pollutes shared staging | `try/finally` cancel/void |
| Status-code-only verdicts | 200 with a float is a breach | Always inspect the body |
| Hardcoded base URL | Breaks across environments | `os.environ["MOVEDOCS_API_BASE"]` |
| Month-approximated interest | Material $ error at portfolio scale | Exact calendar day count |
| Silent self-healing selector updates | Engineers must review | Write to `artifacts/selector_repairs.json` |
| AI-generated code merged without staging run | Untested code in release pipeline | Always execute before merging |
| Raw plaintiff data reaching LLM context | INV-18 — data leakage | Run through `create_guarded_agent_state()` first |
| Hardcoded money values in attacks | Brittle, misses real breaches (INV-19) | Derive from API responses |
| Collapsing generator and judge into one agent | Neither can catch its own mistakes | Keep them permanently separate |

---

## 10. When in Doubt — Escalate, Don't Invent

Stop and ask the human operator when:
- The API returns a shape that doesn't match the spec and you can't tell which is wrong
- An attack's verdict depends on a state-specific legal rule not in `config/rate_caps.json`
- The only way to verify INV-07 requires a real Medicare lien staging cannot simulate
- The browser agent encounters a page it cannot interpret
- An attack accidentally reaches what appears to be real plaintiff data — stop immediately

**A paused agent is cheaper than a wrong report. This applies double in a live demo.**

---

## 11. Release Gate Summary

| Tier | Invariants | Release impact |
|---|---|---|
| CRITICAL | INV-04, INV-06, INV-07, INV-09, INV-11, INV-13 | Hard block — deploy does not proceed |
| HIGH | INV-01, INV-02, INV-03, INV-08, INV-12, INV-15 | Block unless overridden with a ticket |
| MEDIUM | INV-05, INV-10, INV-14, INV-16 | Warning — deploy proceeds, alert created |
| EVAL | INV-17, INV-18, INV-19, INV-20 | Logged — quality dashboard, no block |

---

*Owner: the engineer in the chair. Remember: non-recourse risk, lien priority, integer cents, guardrails first, clean up after yourself. Full architecture in README.md. Design decisions in DECISIONS.md.*