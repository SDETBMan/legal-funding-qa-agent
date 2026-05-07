[![QA Pipeline](https://github.com/SDETBMan/legal-funding-qa-agent/actions/workflows/qa-pipeline.yml/badge.svg)](https://github.com/SDETBMan/legal-funding-qa-agent/actions/workflows/qa-pipeline.yml)

# legal-funding-qa-agent

An autonomous **adversarial QA agent** built with **LangGraph + DSPy + Hypothesis**, attacking 12 financial and legal invariants in a pre-settlement funding API. Produces an auditable JSON report and a **BLOCK / WARN / PASS** release gate signal for CI/CD — not a test suite, an agent that reasons about why a payoff is wrong and explains it.

---

## What it demonstrates

| Concept | Where |
|---|---|
| **Adversarial invariant attacks** | `agent/adversary/attacks.py` — 12 attack functions, one per financial invariant |
| **LangGraph agent orchestration** | `agent/graph.py` — PII preprocess → attack → judge pipeline |
| **DSPy-optimized judge module** | `agent/eval/judge_agent.py` — programmatic prompt optimization for verdict quality |
| **Float-money guardrail (INV-17)** | `agent/eval/judge_agent.py` — rejects HELD verdicts when evidence contains float contamination |
| **Integer cents throughout** | `agent/models/money.py` — no floats in any money field, ever |
| **PII redaction guardrail** | `guardrails/pii_redactor.py` — Presidio-based, strips SSN/email before LLM context |
| **Release gate report** | `artifacts/report.json` — severity-tiered BLOCK/WARN/PASS for CI/CD |
| **Mock API with intentional bugs** | `mock_api/main.py` — 8 seeded invariant violations the agent must find |
| **Jurisdiction usury rate caps** | `config/rate_caps.json` — 51 state caps in basis points |
| **Structured logging** | Every API call logged with structlog — no `print()` |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.11, type hints mandatory |
| HTTP client | httpx (sync) |
| Data models | Pydantic v2 |
| Agent orchestration | LangGraph + LangChain Anthropic |
| Prompt optimization | DSPy (JudgeModule) |
| Property-based attacks | Hypothesis |
| PII redaction | Presidio Analyzer + Anonymizer, spaCy |
| Logging | structlog (JSON-only) |
| Observability | AgentOps |
| Mock API | FastAPI + Uvicorn |
| CI/CD | GitHub Actions |

---

## Quick start

```bash
git clone https://github.com/SDETBMan/legal-funding-qa-agent.git
cd legal-funding-qa-agent
pip install -r requirements.txt

# Copy env and configure
cp .env.example .env

# Start mock API
uvicorn mock_api.main:app --port 8000 &

# Run all 12 attacks
python -m agent.main

# Run unit tests
pytest tests/ -v

# Run guardrails demo (no API needed)
python -m agent.main --demo-guardrails
```

> Copy `.env.example` to `.env` — all required env vars are pre-filled for the mock API.

---

## Invariants under attack

| ID | Rule | Severity | Blast radius |
|---|---|---|---|
| INV-01 | No duplicate active funding on the same case | HIGH | Duplicate disbursement |
| INV-02 | No funding on settled/dismissed/closed cases | HIGH | Unrecoverable loss |
| INV-03 | Attorney acknowledgment before disbursement | HIGH | Legal liability |
| INV-04 | Interest accrues from disbursement_date, not application_date | CRITICAL | Direct $ overcharge |
| INV-05 | Approved funding <= case_max_exposure | MEDIUM | Credit / loss risk |
| INV-06 | Jurisdiction usury rate cap enforced | CRITICAL | Void contract |
| INV-07 | Medicare/Medicaid super-priority in settlement waterfall | CRITICAL | Lienholder liability |
| INV-08 | Lien balance cannot exceed original billed amount | HIGH | Overbilling dispute |
| INV-09 | Plaintiff remainder >= 0 after waterfall | CRITICAL | Company debt |
| INV-10 | Cancelled apps release reserved capacity | MEDIUM | Inventory leak |
| INV-11 | All money fields are integer cents — never floats | CRITICAL | Audit finding |
| INV-12 | Exact calendar day count for interest | HIGH | Material $ error at scale |

---

## Demo output

Running `python -m agent.main` against the mock API produces:

```
rule   | name                                | severity | status   | reasoning
-------+-------------------------------------+----------+----------+------------------------------------------------------
INV-01 | duplicate_funding                   | HIGH     | HELD     | Duplicate correctly rejected.
INV-02 | closed_case_funding                 | HIGH     | HELD     | Application rejected for non-active case status.
INV-03 | disburse_without_attorney_ack       | HIGH     | HELD     | Disbursement blocked without attorney acknowledgment.
INV-04 | interest_from_application_date      | CRITICAL | BREACHED | Plaintiff overcharged by 9 days = 4315 cents ($43.15).
INV-05 | exceeds_case_max_exposure           | MEDIUM   | HELD     | Application rejected for exceeding case_max_exposure.
INV-06 | usury_rate_cap                      | CRITICAL | BREACHED | Contract rate 3500 bps exceeds TX cap of 1800 bps.
INV-07 | waterfall_priority                  | CRITICAL | BREACHED | Medicare paid second despite super-priority.
INV-08 | lien_balance_exceeds_billed         | HIGH     | BREACHED | Lien accepted with balance exceeding original billed.
INV-10 | cancelled_application_capacity_leak | MEDIUM   | BREACHED | Reserved capacity not released after cancel.
INV-11 | float_payoff                        | CRITICAL | BREACHED | total_cents returned as float.
INV-12 | interest_day_count_basis            | HIGH     | BREACHED | days_elapsed off by 9 days.

Release gate: BLOCK
```

7 breaches detected, 5 invariants held. Exit code 1 (BLOCK).

---

## Architecture

```
Explorer → Adversarial Agent → Judge Agent → Report + Release Gate
               ↑
        Synthetic Data
```

| Component | Role |
|---|---|
| Adversarial Agent | Drives edge-case requests against 12 invariants, collects evidence |
| Judge Agent | DSPy-optimized module; grades evidence with float-money guardrail (INV-17) |
| Report + Release Gate | Emits `artifacts/report.json` with BLOCK / WARN / PASS decision |
| Mock API | FastAPI server with 8 intentional bugs for demo and CI |
| Guardrails | PII redaction, rate limiting, retry policy, tool selection, summarization |

---

## Release gate tiers

| Tier | Invariants | CI impact |
|---|---|---|
| CRITICAL | INV-04, INV-06, INV-07, INV-09, INV-11, INV-13 | Hard block — deploy does not proceed |
| HIGH | INV-01, INV-02, INV-03, INV-08, INV-12, INV-15 | Block unless overridden with ticket |
| MEDIUM | INV-05, INV-10, INV-14, INV-16 | Warning — deploy proceeds, alert created |
| EVAL | INV-17, INV-18, INV-19, INV-20 | Logged — quality dashboard, no block |

---

## Mock API bugs (seeded)

| Bug | Invariant | Description |
|---|---|---|
| BUG-01 | INV-11 | `total_cents` returned as `float` instead of `int` |
| BUG-02 | INV-04 | Interest accrues from `application_date`, not `disbursement_date` |
| BUG-03 | INV-07 | Waterfall sorts by `priority_rank` only — no Medicare super-priority |
| BUG-04 | INV-05 | Approve does not re-check `case_max_exposure` |
| BUG-05 | INV-06 | Seed contract rate (3500 bps) exceeds TX usury cap (1800 bps) |
| BUG-06 | INV-08 | Lien `balance > original_billed` accepted |
| BUG-07 | INV-09 | Settlement allows negative plaintiff remainder |
| BUG-08 | INV-10 | Cancelled applications do not release reserved capacity |

---

## File layout

```
agent/
├── adversary/
│   ├── attacks.py                # 12 attack functions — one per invariant
│   ├── invariants.py             # canonical rule list
│   └── red_team.py               # adversarial agents for financial edge cases
├── clients/
│   ├── funding_client.py         # typed httpx wrapper — every call logged
│   ├── lien_client.py            # lien management endpoints
│   └── disbursement_client.py    # settlement disbursement endpoints
├── eval/
│   ├── judge_agent.py            # DSPy JudgeModule + float-money guardrail
│   └── dspy_optimizer.py         # prompt optimization pipeline
├── judge/
│   ├── judge.py                  # LLM verdict + JSON report emitter
│   └── prompts.py                # SHA-256 versioned prompt templates
├── models/
│   ├── case.py, funding.py       # Pydantic v2 domain models
│   ├── lien.py, disbursement.py  # integer cents enforced at model layer
│   └── money.py                  # validate_cents() — rejects floats
├── graph.py                      # LangGraph: PII preprocess → attack → judge
├── main.py                       # CLI entry point
├── guardrails.py                 # create_guarded_agent_state()
├── pii_redactor.py               # Presidio PII detection
├── retry_policy.py               # exponential backoff + fallback model
└── run_limits.py                 # 50 model calls, 200 tool calls per run
guardrails/
├── pii_redactor.py               # SSN, email, financial ID redaction
├── rate_limiter.py               # per-run caps
├── retry_policy.py               # scoped retry config
├── summarization_middleware.py   # compresses history at 80% context window
└── tool_selector_middleware.py   # cheap model filters to top 3 tools
mock_api/
└── main.py                       # FastAPI — 8 intentional bugs for QA agent
config/
└── rate_caps.json                # 51 jurisdiction usury limits (basis points)
tests/
└── test_models.py                # 12 unit tests — money, lien, waterfall models
artifacts/                        # run outputs (gitignored)
├── report.json                   # release gate report
└── attacks.json                  # per-attack evidence
.github/workflows/
└── qa-pipeline.yml               # CI: pytest → mock API → agent → upload report
```

---

## CI/CD Pipeline

The `qa-pipeline.yml` workflow triggers on every push/PR to `main`.

**Jobs:**

| Job | Steps |
|---|---|
| `test` | Checkout → Python 3.11 → `pip install` → `pytest tests/ -v` |
| `qa-gate` | Checkout → Python 3.11 → `pip install` → Start mock API → `python -m agent.main` → Upload `artifacts/report.json` |

Exit code 0 = PASS, exit code 1 = BLOCK. The `qa-gate` job uses the agent's exit code as the pipeline gate.

---

## Domain glossary

| Term | Definition |
|---|---|
| Pre-settlement funding | Non-recourse cash advance to a plaintiff against a pending lawsuit |
| Non-recourse | Company's only collateral is lawsuit proceeds — not the plaintiff |
| Settlement waterfall | Ordered disbursement: Medicare/Medicaid → medical liens → funding payoff → attorney fees → plaintiff remainder |
| Payoff amount | Principal + accrued interest + fees. Exact day count from disbursement_date |
| Lien priority | Legal order in which lienholders are paid. Federal liens are super-priority |
| Attorney acknowledgment | Written confirmation from plaintiff's attorney required before disbursement |
| Case max exposure | Maximum the platform will advance, typically a % of estimated settlement |

---

## Design decisions

- **Why LangGraph instead of pytest?** The agent reasons about *why* a payoff is wrong (day count? rate? fee?) and explains it — pytest would only show a failure.
- **Why DSPy instead of hand-tuned prompts?** Prompts degrade silently when response shapes change. DSPy turns the Judge into a module with a measurable eval score — regression is detectable.
- **Why integer cents throughout?** Floating-point in payoff math is a compliance finding in regulated legal funding — integer arithmetic is exact, no alternative.
- **Why adversarial attacks instead of assertions?** Traditional tests assert what you expect. Adversarial attacks surface what you didn't model.

---

## License & Attribution

MIT License — Copyright 2026 Brian Padgett

This framework was independently developed prior to any employment engagement.
All code, architecture decisions, and documentation represent original work
authored and committed by Brian Padgett. Commit history and timestamps are
the authoritative record of authorship.
