import os
from dotenv import load_dotenv
from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from deepeval.metrics import GEval
from deepeval.test_case import SingleTurnParams
from deepeval.models import AnthropicModel

load_dotenv()

api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise RuntimeError("Missing ANTHROPIC_API_KEY. Add it to your .env file or environment before running deepeval.")

# The judge is pinned to an explicit version on purpose: if the judge drifts,
# a score change can't be attributed to the product or to the judge.
#
# claude-opus-4-8 rather than claude-opus-5: deepeval reads message.content[0].text
# unconditionally, and models with thinking on by default (opus-5, sonnet-5) put a
# ThinkingBlock at index 0 -> AttributeError. Opus 4.8 has thinking off unless asked.
# To use opus-5 instead, pass generation_kwargs={"thinking": {"type": "disabled"}}.
#
# Do not pass temperature — current Opus models reject sampling params with a 400.
judge_model = AnthropicModel(
    model=os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8"),
    api_key=api_key,
    cost_per_input_token=5 / 1_000_000,
    cost_per_output_token=25 / 1_000_000,
)

# Define GEval using Claude as the model judge
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

def test_itinerary_eval():
    test_case = LLMTestCase(
        input="Schedule a 1-day trip to Tokyo visiting Ghibli Museum and Shibuya Crossing.",
        actual_output="Morning: Shibuya Crossing. Afternoon: Ghibli Museum.",
        expected_output="Morning: Ghibli Museum. Afternoon: Shibuya Crossing."
    )
    assert_test(test_case, [correctness_metric])
