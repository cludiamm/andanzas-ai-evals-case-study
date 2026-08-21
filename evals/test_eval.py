import json
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from deepeval.metrics import GEval
from deepeval.test_case import SingleTurnParams
from deepeval.models import AnthropicModel, GeminiModel

from must_visit_metric import MustVisitMetric

load_dotenv()

# The judge is pinned to an explicit version on purpose: if the judge drifts,
# a score change can't be attributed to the product or to the judge.
#
# Default judge is Gemini (see CLAUDE.md). Set JUDGE_PROVIDER=anthropic in
# .env to fall back to Claude — e.g. when the Gemini free-tier daily quota
# (20 requests/model/day) is exhausted.
judge_provider = os.getenv("JUDGE_PROVIDER", "gemini").lower()

if judge_provider == "gemini":
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY. Add it to your .env file or environment before running deepeval.")
    # Pass api_key explicitly (rather than relying on ambient GOOGLE_API_KEY /
    # ADC) so GeminiModel talks to the plain Gemini API instead of falling back
    # to Vertex AI, which needs GCP credentials this environment doesn't have —
    # that mismatch is what previously surfaced as a 401 from GEval.
    judge_model = GeminiModel(
        model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
        api_key=api_key,
    )
elif judge_provider == "anthropic":
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("Missing ANTHROPIC_API_KEY. Add it to your .env file or environment before running deepeval.")
    # claude-opus-4-8 rather than claude-opus-5: deepeval reads message.content[0].text
    # unconditionally, and models with thinking on by default (opus-5, sonnet-5) put a
    # ThinkingBlock at index 0 -> AttributeError. Opus 4.8 has thinking off unless asked.
    # Do not pass temperature — current Opus models reject sampling params with a 400.
    judge_model = AnthropicModel(
        model=os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8"),
        api_key=api_key,
        cost_per_input_token=5 / 1_000_000,
        cost_per_output_token=25 / 1_000_000,
    )
else:
    raise RuntimeError(f"Unknown JUDGE_PROVIDER={judge_provider!r}; expected 'gemini' or 'anthropic'.")

# Define GEval using the configured judge model.
#
# Must-visit preservation is judged deterministically by MustVisitMetric
# below, not here — asking the LLM judge to also weigh in on it would let
# the two mechanisms disagree with no clear tie-breaker. GEval's criteria is
# scoped to what's left: opening-hours plausibility, pacing/fatigue balance,
# and the collaborative Co-Admin tone (propose, don't unilaterally cut).
correctness_metric = GEval(
    name="Itinerary Correctness",
    criteria=(
        "Determine if the actual itinerary respects venue opening hours, "
        "keeps a balanced pace (avoiding overly exhausting days), and "
        "maintains a collaborative Co-Admin tone that proposes options "
        "rather than unilaterally cutting items."
    ),
    evaluation_params=[
        SingleTurnParams.INPUT,
        SingleTurnParams.ACTUAL_OUTPUT,
        SingleTurnParams.EXPECTED_OUTPUT
    ],
    model=judge_model
)

DATASET_PATH = Path(__file__).resolve().parent.parent / "data" / "golden_dataset.json"

# ITINERARY_VARIANT picks which fixture set generate_actual_output() reads
# from, so the baseline (Phase 1) and optimized/hybrid (Phase 2) sweeps stay
# independently reproducible instead of overwriting each other.
#   baseline  -> data/actual_outputs.json      (zero-shot, no system prompt)
#   optimized -> data/optimized_outputs.json   (prompts/system_prompt_v2.md)
OUTPUTS_PATHS = {
    "baseline": Path(__file__).resolve().parent.parent / "data" / "actual_outputs.json",
    "optimized": Path(__file__).resolve().parent.parent / "data" / "optimized_outputs.json",
}
itinerary_variant = os.getenv("ITINERARY_VARIANT", "baseline").lower()
if itinerary_variant not in OUTPUTS_PATHS:
    raise RuntimeError(
        f"Unknown ITINERARY_VARIANT={itinerary_variant!r}; expected one of {sorted(OUTPUTS_PATHS)}."
    )
ACTUAL_OUTPUTS_PATH = OUTPUTS_PATHS[itinerary_variant]

def load_golden_dataset():
    with open(DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)

def load_actual_outputs():
    with open(ACTUAL_OUTPUTS_PATH, encoding="utf-8") as f:
        return json.load(f)

golden_dataset = load_golden_dataset()
actual_outputs = load_actual_outputs()


def generate_actual_output(case: dict) -> str:
    # PLACEHOLDER: swap this for a real call to Andanzas (or the model under
    # test) using case["input_user_request"]. Until that's wired up, this
    # pulls from the fixture set selected by ITINERARY_VARIANT above.
    test_case_id = case["test_case_id"]
    if test_case_id not in actual_outputs:
        raise KeyError(f"No actual_output fixture for {test_case_id!r} in {ACTUAL_OUTPUTS_PATH}")
    return actual_outputs[test_case_id]


def build_must_visit_metric(case: dict) -> MustVisitMetric:
    check = case["constraints"]["must_visit_check"]
    return MustVisitMetric(
        keywords=check["keywords"],
        required_min_distinct_days=check["required_min_distinct_days"],
    )


@pytest.mark.parametrize(
    "case",
    golden_dataset,
    ids=[item["test_case_id"] for item in golden_dataset],
)
def test_itinerary_eval(case):
    test_case = LLMTestCase(
        input=case["input_user_request"],
        actual_output=generate_actual_output(case),
        expected_output=case["expected_output_ground_truth"]
    )
    must_visit_metric = build_must_visit_metric(case)
    assert_test(test_case, [correctness_metric, must_visit_metric])
