import os
from dotenv import load_dotenv
from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from deepeval.metrics import GEval
from deepeval.test_case import SingleTurnParams
from deepeval.models import GeminiModel

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("Missing GEMINI_API_KEY. Add it to your .env file or environment before running deepeval.")

# Use a currently supported Gemini model name for the Google GenAI API.
gemini_model = GeminiModel(
    model=os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
    api_key=api_key
)

# Define GEval using Gemini as the model judge
correctness_metric = GEval(
    name="Itinerary Correctness",
    criteria="Determine if the actual itinerary respects opening hours and must-visit preferences.",
    evaluation_params=[
        SingleTurnParams.INPUT, 
        SingleTurnParams.ACTUAL_OUTPUT, 
        SingleTurnParams.EXPECTED_OUTPUT
    ],
    model=gemini_model
)

def test_itinerary_eval():
    test_case = LLMTestCase(
        input="Schedule a 1-day trip to Tokyo visiting Ghibli Museum and Shibuya Crossing.",
        actual_output="Morning: Shibuya Crossing. Afternoon: Ghibli Museum.",
        expected_output="Morning: Ghibli Museum. Afternoon: Shibuya Crossing."
    )
    assert_test(test_case, [correctness_metric])