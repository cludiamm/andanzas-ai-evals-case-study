# Andanzas AI Evals: Constrained Itinerary Generation & Quality Benchmarking

An automated evaluation framework designed to benchmark LLM travel co-admins against strict deterministic calendar, preference, and fatigue constraints.

---

## Executive Summary

Generative AI models excel at creative travel recommendations, but frequently fail in production due to **non-deterministic constraint violations**: hallucinating venue operating hours, ignoring user must-visit preferences, or scheduling overly exhausting itineraries.

This project implements an **Automated Evals Pipeline** for **Andanzas**—an AI-native trip planning system. Using `DeepEval` and `LLM-as-a-Judge` scoring, this suite measures model accuracy, preference preservation, and balance guardrails to ensure production-grade reliability before itinerary outputs reach users.

---

## The Business Problem & System Constraints

Unlike traditional travel apps that auto-generate rigid schedules, the **Andanzas methodology** positions AI as a **Co-Admin**—a collaborative partner operating under strict rules:

1. **Hard Constraint (0% Tolerance):** Opening hours override geography. A schedule that places a venue outside its operating window is a critical system failure.
2. **Inviolable Preference (Must-Visit Exemption):** Every traveller receives one inviolable "Must-Visit" venue that cannot be dropped unless explicit, computable cost/distance thresholds are breached.
3. **Pacing Guardrails:** Maximum of 2 museums per day to prevent trip fatigue.
4. **Co-Admin Role Boundary:** The system proposes options; it never auto-cuts or oversteps user autonomy.

---

## Evaluation Architecture

The test suite evaluates LLM outputs across a **Golden Dataset ($N=3$)** of real, previously-booked multi-city trips — deliberately deep rather than broad: each case carries dozens of concrete hard bounds (timed tickets, closing days, ferry departures) pulled from the traveller's actual bookings, rather than a large volume of shallow synthetic prompts.

```text
               +----------------------------------+
               |  Golden Dataset Input (User)     |
               +----------------------------------+
                                |
                                v
               +----------------------------------+
               |  LLM Generation (Under Test)     |
               +----------------------------------+
                                |
                                v
               +----------------------------------+
               |      DeepEval Evaluation Engine   |
               +----------------------------------+
                                /                  \
                               /                    \
   +--------------------------+              +--------------------------+
   | Deterministic Checks     |              | LLM-as-a-Judge           |
   | (Python Logic)           |              | (G-Eval)                 |
   +--------------------------+              +--------------------------+
   | - Must-Visit Present     |              | - Opening Hours          |
   | - Must-Visit Duration    |              | - Fatigue Pacing         |
   | - (day-count check)      |              | - Co-Admin Tone          |
   +--------------------------+              +--------------------------+
```

### Metrics & Scoring

Two metrics run per test case, deliberately scoped so they never grade the
same thing twice — see [Key Findings](#key-findings--product-recommendations)
for why that split matters more than it might look.

| Metric | Evaluation Type | Pass Criteria | Threshold |
| :--- | :--- | :--- | :--- |
| **Must-Visit Preservation** | Deterministic Python (`MustVisitMetric`) | Must-visit venue(s) present **and** discussed across the required number of distinct day/date mentions — not just present anywhere in the text | Binary, $1.0$ |
| **Itinerary Correctness** | G-Eval (LLM-as-judge) | Opening-hours plausibility, fatigue/pacing balance, and collaborative Co-Admin tone | Score $\ge 0.5$ |

The judge model defaults to **Gemini** (`gemini-3.6-flash`), with Claude
(`claude-opus-4-8`) as a configurable fallback for when Gemini's free-tier
daily quota is exhausted (`JUDGE_PROVIDER=anthropic` in `.env`). Results
below were produced with the Gemini judge.

---

## Experimental Results

Evaluations were conducted using `Gemini` (`gemini-3.6-flash`) as the `LLM-as-a-Judge` via `DeepEval` (Golden Dataset $N=3$). The goal was to evaluate the trade-off between **Accuracy**, **Cost**, and **Latency** when moving from a zero-shot baseline to an optimized system prompt, and then to a hybrid architecture that adds a deterministic guardrail on top.

| Model Architecture & Strategy | Pass Rate | Avg Judge Latency | Generation Cost / Itinerary | Judge Cost / 1k Evals |
| :--- | :--- | :--- | :--- | :--- |
| **Baseline (Unconstrained Zero-Shot)** | 66.7% (2/3) | 29.0s | $0 (hand-authored fixtures) | $3.99 |
| **Optimized (System Prompt Only)** | 100% (3/3) | 19.9s | $0.089 (Claude Opus) | $6.59 |
| **Hybrid (Prompt + Deterministic Guardrail)** | 100% (3/3) | 19.9s | $0.089 (Claude Opus) | $6.59 |

**Reading this table:**
- **Generation Cost** is what it costs to *produce* one itinerary — the number that scales with customer volume and belongs in pricing. **Judge Cost** is what it costs to *QA* one itinerary against the golden set — an infrastructure/testing cost that runs on a schedule (CI, nightly regression), not per customer. Blending these into one "cost" figure would hide that distinction, which is why they're reported separately rather than summed.
- Judge Cost is deepeval's list-price estimate for the configured model (`tokens × Gemini's published per-token rate`), not an actual bill — this project stayed within Gemini's free tier, so nothing was actually charged for judging. Treat it as a capacity-planning number for when free-tier volume is exceeded, not today's spend.
- The Optimized and Hybrid rows show identical pass rates because, across these 3 cases, the LLM judge and the deterministic guardrail never disagreed — see the finding below on why that's not a reason to remove the deterministic check.
- $N=3$ is too small to treat any of these percentages as statistically stable; read this table as a directional proof-of-concept (does the architecture change move the needle at all, and in which direction) rather than a production SLA.

### Baseline Failure Taxonomy

The unconstrained baseline run (66.7% pass rate) revealed critical production risks when AI models attempt to build itineraries without deterministic guardrails:
1. **Severe Temporal/Spatial Failures:** On a 93-day long-horizon itinerary, the unconstrained model compressed a non-negotiable 4-day Sintra palace circuit into a single day, ignoring physical travel constraints.
2. **Ignorance of Operating Rules & Schedules:** The baseline generator scheduled the *Museo Reina Sofía* in Madrid on a Tuesday morning, despite the museum being strictly closed on Tuesdays.
3. **Loss of Operational Grounding:** On island-hopping scenarios, the model assumed digital seamless transit, ignoring explicit constraints requiring in-person ticket collection at local travel agencies prior to boarding single-daily-sailing ferries.
4. **Fatigue/Pacing Overload:** On a heavy multi-site day, the baseline stacked a full-day combined Auschwitz-Birkenau + Wieliczka Salt Mines tour together with an additional museum in the same afternoon — a pairing the golden data's own edge-case notes flag as something "should never" happen, regardless of opening hours technically allowing it.

### Guardrail in Action: The Sintra Fix, Before and After

The same test case (`trip_02_europa_solo_iberia_uk`), evaluated by both metrics, before and after the Phase 2 changes:

| | Baseline | Optimized + Hybrid |
| :--- | :--- | :--- |
| **Itinerary excerpt** | *"Sintra (10–11 Apr): a single full day combining Palácio da Pena, Castelo dos Mouros, Quinta da Regaleira and Palácio de Monserrat via local buses, then straight on to Porto."* | *"Day (10 Apr, Sintra): Arrival + circuit day 1... Day (11 Apr, Sintra): Quinta da Regaleira 10:00 → Palácio de Monserrat 12:30... Day (12 Apr, Sintra): Palácio da Pena 09:30 → Castelo dos Mouros 14:30... Day (13 Apr, Sintra): circuit day 4..."* |
| **GEval verdict** | 0.30 — FAIL. *"rushes Sintra... into a single jammed day... lacks a collaborative Co-Admin tone."* | 0.90 — PASS |
| **MustVisitMetric verdict** | 0.0 — FAIL. *"only 2 distinct day/date mention(s) found nearby (need >= 4)."* | 1.0 — PASS. *"7 distinct day/date mention(s) (>= 4 required)."* |

Both the must-visit name ("Sintra" / "Palácio da Pena") and the word "Sintra" itself are present in *both* versions — a presence-only check, as originally scoped, would have passed the baseline. It's the duration check specifically that catches the compression.

### Key Findings & Product Recommendations

1. **Zero-shot models consistently fail on temporal constraints.** Relying entirely on probabilistic models to handle calendar math, opening days, and strict routing logic leads to unacceptable failure rates (0.2–0.3/1.0 on complex trips) — and the failures aren't random noise, they're the exact "must-visit compressed," "closed on this day," "impossible connection" patterns the Co-Admin methodology exists to prevent.
2. **Presence is not preservation.** A check that only asks "does the must-visit venue's name appear in the output" would have passed the baseline's compressed Sintra plan — the venue name survived, the four days didn't. The deterministic guardrail had to check *duration*, not just *presence*, to catch the actual bug.
3. **Hybrid system design is required, and the split is durable, not just cost-driven.** Probabilistic judging is well-suited to qualities that require interpretation (pacing, tone) and poorly suited to a fact that must never be wrong. Even if a larger sample showed the judge and the deterministic check agreeing 100% of the time, that would be a reason to trust the judge's calibration on this dimension — not a reason to remove the deterministic backstop for a rule the product defines as 0%-tolerance. LLM judges can drift between model versions or re-runs in a way that pure code cannot; the guardrail's value is in the tail case, not the average case.
4. **Generation cost and judge cost are different budget lines.** Judging cost (~$6.59/1k evals, at list price) is a testing/QA overhead that runs on a schedule, not per customer. Generation cost (~$0.089/itinerary here) is what actually belongs in a pricing model, since it scales with usage. Conflating the two would overstate the per-customer cost of running Andanzas by roughly two orders of magnitude.
5. **A cheap deterministic check can gate an expensive judge call.** Since `MustVisitMetric` is free and instant, a production pipeline could run it first and skip the paid GEval call entirely when it already fails — worth prototyping in a later phase, not built here.

---

## Repository Structure

```text
.
├── README.md                          # Case Study Documentation
├── requirements.txt                   # Project Dependencies
├── prompts/
│   └── system_prompt_v2.md            # Optimized Co-Admin system prompt (Phase 2, Step 2)
├── scripts/
│   ├── generate_optimized_outputs.py  # Calls Anthropic to produce data/optimized_outputs.json
│   └── run_evaluation_sweep.py        # Runs both metrics against a variant, reports pass rate/latency/cost
├── data/
│   ├── golden_dataset.json            # Ground-truth benchmark data from real trips (incl. must_visit_check)
│   ├── actual_outputs.json            # Baseline (zero-shot) itinerary fixtures
│   └── optimized_outputs.json         # Optimized (system-prompted) itinerary fixtures
└── evals/
    ├── test_eval.py                   # Hybrid DeepEval test suite (GEval + MustVisitMetric)
    ├── must_visit_metric.py           # Deterministic Must-Visit Preservation metric
    └── test_must_visit_metric.py      # Unit tests for the deterministic metric
```

---

## How to Run the Evaluation Suite Locally

### 1. Prerequisites & Installation
Ensure you have Python 3.10+ installed.

```bash
# Clone repository
git clone [https://github.com/YOUR_USERNAME/andanzas-ai-evals-case-study.git](https://github.com/YOUR_USERNAME/andanzas-ai-evals-case-study.git)
cd andanzas-ai-evals-case-study

# Set up virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_gemini_api_key      # default judge
ANTHROPIC_API_KEY=your_anthropic_api_key  # judge fallback + itinerary generation

# Optional overrides:
# JUDGE_PROVIDER=anthropic     # fall back to Claude if Gemini's free-tier daily quota is exhausted
# ITINERARY_VARIANT=optimized  # evaluate data/optimized_outputs.json instead of the baseline fixtures
```

### 3. Run the Eval Suite

```bash
# All evals
venv\Scripts\python.exe -m pytest -v

# Just the hybrid suite (GEval + deterministic Must-Visit metric)
venv\Scripts\python.exe -m pytest evals\test_eval.py -v

# Same suite, against the optimized/hybrid fixtures instead of the baseline
set ITINERARY_VARIANT=optimized
venv\Scripts\python.exe -m pytest evals\test_eval.py -v

# Deterministic metric only, no API calls (fast, free, safe to run anytime)
venv\Scripts\python.exe -m pytest evals\test_must_visit_metric.py -v
```

### 4. Regenerate Fixtures (optional)

```bash
# Re-generate data/optimized_outputs.json via Anthropic (spends real API credits)
venv\Scripts\python.exe scripts\generate_optimized_outputs.py

# Report pass rate, latency, and cost for a given variant without pytest's assertion-per-case flow
venv\Scripts\python.exe scripts\run_evaluation_sweep.py --variant optimized
```