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

# Define GEval using the configured judge model
correctness_metric = GEval(
    name="Itinerary Correctness",
    criteria="Determine if the actual itinerary respects opening hours and must-visit preferences.",
    evaluation_params=[
        SingleTurnParams.INPUT,
        SingleTurnParams.ACTUAL_OUTPUT,
        SingleTurnParams.EXPECTED_OUTPUT
    ],
    model=judge_model
)

DATASET_PATH = Path(__file__).resolve().parent.parent / "data" / "golden_dataset.json"
ACTUAL_OUTPUTS_PATH = Path(__file__).resolve().parent.parent / "data" / "actual_outputs.json"

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
    # pulls from data/actual_outputs.json — a fixture set of independently
    # drafted itineraries (not the ground truth) so the judge has real work
    # to do.
    test_case_id = case["test_case_id"]
    if test_case_id not in actual_outputs:
        raise KeyError(f"No actual_output fixture for {test_case_id!r} in {ACTUAL_OUTPUTS_PATH}")
    return actual_outputs[test_case_id]


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
    assert_test(test_case, [correctness_metric])
