# Evals Playbook: Injecting Automated Evaluation into an AI Product

This is a reusable methodology, extracted from building the Andanzas evals
suite end to end. It's written so the steps transfer to a different product:
Andanzas-specific facts (Sintra, museum caps, Gemini/Claude) are the worked
example, not the method itself.

The core idea threading through both phases: **an eval suite isn't one
thing.** It's a combination of a judgment layer (an LLM reading output the
way a human reviewer would) and a fact-checking layer (code that is either
right or wrong, with no in-between). Most of the hard decisions in this
project were about figuring out which layer a given rule belonged to, and
what breaks when you get that assignment wrong.

---

## Phase 1: Setup & Baseline

The goal of Phase 1 isn't to catch bugs yet — it's to build the instrument
that will let you see them, and to get one honest, unflattering number that
everything later gets measured against.

### Step 1 — Write down the product's non-negotiable rules first, in plain language

Before any code: what does this product promise that must never be broken?
For Andanzas that was four rules (opening hours are absolute, a must-visit
item is inviolable, ≤2 museums/day, propose-don't-auto-cut). Write these as
plain sentences a non-engineer could read, not as code. Everything else in
the suite — the dataset, the metrics, the prompt — exists to check these
rules; skipping this step means building an eval suite that measures
something, just not necessarily the thing that matters.

### Step 2 — Build a small, deep golden dataset before a large, shallow one

Andanzas' golden set is 3 cases, not 300 — and that was the right call, not
a shortcut. Each case is a real, previously-booked trip carrying dozens of
concrete hard bounds (exact ticket times, confirmation numbers, closing
days) pulled from an actual itinerary, rather than a synthetic prompt
someone imagined. A small set of real, constraint-dense cases surfaces more
real failure modes than a large set of generic ones, and it's cheap enough
to hand-verify every field.

**Practical rule:** if you can't personally explain why every constraint in
a golden case is there, it's not ready to be a golden case.

### Step 3 — Wire the harness with a pinned, swappable judge

Key decisions made here, in order of importance:
- **Pin the judge to an explicit model version.** If the judge's underlying
  model silently updates, a score change later can't be attributed to the
  product or the judge — you lose the ability to trust your own trend line.
- **Make the judge provider swappable**, not hardcoded — this project
  defaults to Gemini and falls back to Claude via an env var, because free
  API tiers have daily quotas and a suite that halts entirely when one
  provider is rate-limited isn't a suite you can rely on.
- **Keep test cases as data, separate from metric code.** The golden
  dataset is JSON; the metrics are Python. Neither should know about the
  other's internals — a metric takes a `test_case` and returns a score, full
  stop.

### Step 4 — Establish a baseline against realistic (not idealized) outputs

Run the suite against outputs that represent what the product *actually*
produces today — not hand-picked good examples. Andanzas' baseline used
independently-drafted itineraries, not the golden ground truth, specifically
so the judge had real work to do. A baseline run against outputs designed to
pass will tell you your suite works; it won't tell you anything about your
product.

### Step 5 — Read every failure for a pattern before writing any fix

Don't jump to remediation. The baseline run's value is the *taxonomy* of
failure it reveals: Andanzas' baseline (66.7% pass rate) sorted into four
distinct patterns — severe compression of a multi-day anchor, ignorance of
closing days, missing real-world booking friction (in-person ferry ticket
pickup), and fatigue/pacing overload. Each pattern became a specific,
falsifiable target for Phase 2, rather than a vague "make it better."

---

## Phase 2: Optimization & Guardrail Engineering

Phase 1 tells you the product is broken and roughly how. Phase 2 is where
you decide, rule by rule, *how much you trust an LLM to check its own
work* — and build accordingly.

### Step 1 — Sort each failure into "judgment call" or "provable fact," and build a deterministic metric for the latter

For every rule from Phase 1 Step 1, ask: can a human disagree in good faith
about whether this was violated? Tone, pacing, and "does this feel
collaborative" are judgment calls — an LLM judge is the right tool. "Did the
must-visit anchor keep its full required duration" is not a judgment call —
it's countable, and an LLM grading its own probabilistic best guess at a
countable fact is exactly the failure mode you're trying to eliminate.

**The trap to avoid, found the hard way in this project:** a metric that
only checks *presence* ("does the venue's name appear in the text") is not
the same as checking *preservation*. Andanzas' baseline compressed a 4-day
Sintra anchor into 1 day while still naming "Sintra" and "Palácio da Pena"
verbatim — a presence-only check would have passed it. The deterministic
metric had to count distinct day/date mentions near the keyword, not just
detect the keyword, to catch the actual bug. **Before shipping a
deterministic guardrail, run it against the specific broken example that
motivated building it, and confirm it actually fails that example.** A
guardrail that can't catch the bug it was named after is worse than no
guardrail — it creates false confidence.

### Step 2 — Engineer the prompt against the specific failure taxonomy, not generically

Don't write a generic "be careful and accurate" system prompt. Target the
exact patterns from Phase 1 Step 5: if the failure was silent compression,
the fix is a structural rule that makes compression *hard to phrase*
("one explicit day-block per calendar day," "never summarize multiple days
into one sentence") — not just an instruction to "be thorough." Pair every
hard rule with a self-check instruction that mirrors what your deterministic
metric checks (count days per anchor, verify against the requested count) —
the same failure mode gets attacked from both the probabilistic and
deterministic side.

**A second trap, also found the hard way:** an aggressive "don't guess, flag
uncertainty instead of fabricating" instruction will cause the model to
*refuse to produce output* if your pipeline doesn't actually hand it the
facts it needs. Early in this project, the optimized prompt made the
generator ask clarifying questions instead of producing itineraries — not
because the prompt was wrong, but because the generation script only passed
a prose summary and left out the structured constraints (exact dates, ticket
numbers) the golden data was itself built from. **Before concluding a prompt
"failed," audit exactly what context the model actually received** — a
strict prompt correctly refusing to guess, given incomplete input, looks
identical to a prompt that's broken.

### Step 3 — Combine metrics so no two of them grade the same thing

Once a deterministic metric exists for a rule, narrow the LLM judge's
criteria to explicitly exclude it. Two metrics quietly grading the same
fact means disagreements have no tie-breaker, and it obscures which
mechanism actually caught a given bug. Scope each metric to what it's
best at, document the split, and run them together, not as substitutes.

### Step 4 — Decouple generation from evaluation before comparing "before" and "after"

Freeze generated outputs into a fixture file rather than calling the model
under test live inside every eval run. This matters for a specific
methodological reason, not just cost: if generation happens fresh on every
test run, a pass-rate change between two runs is ambiguous — is it the
prompt, or did the model just happen to sample differently that time? A
frozen snapshot means the only thing that can change between re-runs of the
same fixture is judge variance, isolating exactly the variable you're trying
to measure. Live, on-every-request generation is a different, valid pattern
(production monitoring) — just not the one that produces a defensible
before/after comparison.

### Step 5 — Report real numbers, with the caveats that make them trustworthy

- **Separate cost types.** Cost to *generate* one output (scales with
  customer volume, belongs in pricing) is a different budget line from cost
  to *judge* one output against a golden set (a testing/QA overhead that
  runs on a schedule). Blending them into one number overstates or
  understates both, depending which dominates.
- **State whether a cost figure is a real bill or a list-price estimate.**
  Free-tier usage that stays under quota costs $0 today; the theoretical
  paid-tier cost is still useful for capacity planning, but say which one
  you're reporting.
- **Don't let small-N results imply more precision than they have.** A
  66.7%-to-100% jump on 3 cases is directional evidence, not a production
  SLA — say so explicitly rather than let a clean percentage imply
  statistical weight it doesn't carry.
- **Don't remove a deterministic guardrail just because it currently agrees
  with the probabilistic judge.** High agreement is evidence the judge is
  well-calibrated on that dimension; it isn't a reason to delete the one
  mechanism in the stack that's immune to model drift, especially for a
  rule the product defines as zero-tolerance. The guardrail's value is in
  the disagreement case, and a small sample will rarely have shown you one.

---

## Cross-cutting lessons (mistakes made during this project, generalized)

1. **Verify your own tooling's output before reporting results.** A pytest
   run's terminal output got truncated mid-traceback during this project,
   and two unrelated failures' text got visually spliced together in a way
   that looked like a real bug (a Korea/Japan test case's failure appearing
   to describe an Auschwitz constraint from a different case). Redirect to
   a file and re-read cleanly rather than trust a truncated stream, before
   drawing conclusions from it.
2. **A transient infrastructure error (a judge API 503) is not a metric
   result.** Don't record "failed" for a case that never actually got
   scored — distinguish "the product failed the check" from "the check
   itself didn't run."
3. **Cheap, deterministic checks can gate expensive, probabilistic ones.**
   Not built in this project, but worth naming: since a deterministic
   metric is free and instant, running it first and skipping the paid judge
   call when it already fails is a real cost optimization for later.
4. **Every non-trivial claim in a written case study is a liability if
   unverified.** This project's own README, before this pass, claimed a
   dataset size that didn't match the actual file, a judge model that
   didn't match the actual code, and pending results that were never
   resolved. Treat documentation the same way you'd treat a test: it can be
   wrong, and it's worth re-reading against the actual repo state before
   calling it done.

---

## Quick-start checklist for a new process

1. Write the product's non-negotiable rules in plain language.
2. Build a small (5–20 case), deep golden dataset from real examples, not synthetic ones.
3. Wire a pinned, swappable LLM judge; keep data and metric code separate.
4. Run a baseline against realistic (not cherry-picked) outputs.
5. Read the failures into a named taxonomy before writing any fix.
6. For each rule: judgment call → LLM judge; provable fact → deterministic code metric.
7. Validate every deterministic metric against the specific bug that motivated it, before trusting it.
8. Target prompt fixes at the named failure taxonomy, not generically; audit what context the model actually receives before blaming the prompt.
9. Scope metrics so none of them grade the same fact twice.
10. Freeze generated outputs before comparing before/after — don't regenerate live inside the comparison.
11. Report cost and latency with their type and precision caveats stated, not just the number.
12. Re-read every claim in the written report against the current repo state before publishing it.

---

## Appendix: this repo, mapped to the steps above

| Step | File(s) |
| :--- | :--- |
| Golden dataset | `data/golden_dataset.json` |
| Baseline fixtures | `data/actual_outputs.json` |
| Optimized fixtures | `data/optimized_outputs.json` |
| Harness / hybrid test suite | `evals/test_eval.py` |
| Deterministic metric | `evals/must_visit_metric.py`, `evals/test_must_visit_metric.py` |
| Optimized system prompt | `prompts/system_prompt_v2.md` |
| Generation (frozen-fixture producer) | `scripts/generate_optimized_outputs.py` |
| Comparison sweep | `scripts/run_evaluation_sweep.py` |
| Results write-up | `README.md` |
