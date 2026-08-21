import json
from pathlib import Path

import pytest
from deepeval.test_case import LLMTestCase

from must_visit_metric import MustVisitMetric

DATASET_PATH = Path(__file__).resolve().parent.parent / "data" / "golden_dataset.json"
ACTUAL_OUTPUTS_PATH = Path(__file__).resolve().parent.parent / "data" / "actual_outputs.json"

golden_dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
actual_outputs = json.loads(ACTUAL_OUTPUTS_PATH.read_text(encoding="utf-8"))


def _metric_for(case: dict) -> MustVisitMetric:
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
def test_ground_truth_passes(case):
    # The metric must not false-fail a correct itinerary — every golden
    # ground truth in the dataset already satisfies its own must-visit
    # requirement by construction.
    metric = _metric_for(case)
    test_case = LLMTestCase(
        input=case["input_user_request"],
        actual_output=case["expected_output_ground_truth"],
    )
    metric.measure(test_case)
    assert metric.success, metric.reason


def test_sintra_compression_bug_is_caught():
    # This is the flagship regression: the baseline fixture mentions
    # "Palácio da Pena" / "Sintra" by name, so a presence-only check would
    # incorrectly pass it, even though the 4-day anchor was compressed into
    # a single day (10-11 Apr instead of 10-13 Apr).
    case = next(c for c in golden_dataset if c["test_case_id"] == "trip_02_europa_solo_iberia_uk")
    metric = _metric_for(case)
    test_case = LLMTestCase(
        input=case["input_user_request"],
        actual_output=actual_outputs["trip_02_europa_solo_iberia_uk"],
    )
    metric.measure(test_case)
    assert not metric.success
    assert "compressed" in metric.reason


def test_missing_keyword_fails_on_presence():
    metric = MustVisitMetric(keywords=["Atlantis"], required_min_distinct_days=1)
    test_case = LLMTestCase(
        input="irrelevant",
        actual_output="Day 1: Madrid. Day 2: Lisbon.",
    )
    metric.measure(test_case)
    assert not metric.success
    assert "Missing must-visit keyword" in metric.reason


def test_partial_keyword_list_fails_when_one_venue_missing():
    # trip_03's anchor is the full Cyclades chain (all four islands); losing
    # even one island should fail the check, not just a total day count.
    metric = MustVisitMetric(
        keywords=["Santorini", "Milos", "Naxos", "Mykonos"],
        required_min_distinct_days=4,
    )
    test_case = LLMTestCase(
        input="irrelevant",
        actual_output="25 Sep: Santorini. 26 Sep: Milos. 27 Sep: Naxos.",
    )
    metric.measure(test_case)
    assert not metric.success
    assert "Mykonos" in metric.reason
