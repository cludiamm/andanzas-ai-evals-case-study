"""Run the eval suite against one itinerary variant and report both the
GEval-only view and the Hybrid (GEval + deterministic) view from a single
pass -- so comparing them doesn't mean paying for the judge twice.

The README's results table treats these as two separate rows ("Optimized
LLM + System Prompting" vs "Hybrid (LLM + Python Deterministic Check)")
because they represent different guardrail architectures, but both are
just different ways of reading the same per-case metric results, so one
judge call per case is enough for both.

Usage:
    venv\\Scripts\\python.exe scripts\\run_evaluation_sweep.py --variant baseline
    venv\\Scripts\\python.exe scripts\\run_evaluation_sweep.py --variant optimized
"""
import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evals"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=["baseline", "optimized"], default="baseline")
    args = parser.parse_args()
    os.environ["ITINERARY_VARIANT"] = args.variant

    from deepeval.test_case import LLMTestCase
    import test_eval as te  # imported after ITINERARY_VARIANT is set, since test_eval reads it at import time

    results = []
    for case in te.golden_dataset:
        test_case = LLMTestCase(
            input=case["input_user_request"],
            actual_output=te.generate_actual_output(case),
            expected_output=case["expected_output_ground_truth"],
        )
        must_visit_metric = te.build_must_visit_metric(case)

        start = time.perf_counter()
        te.correctness_metric.measure(test_case)
        latency = time.perf_counter() - start

        must_visit_metric.measure(test_case)

        results.append(
            {
                "id": case["test_case_id"],
                "geval_score": te.correctness_metric.score,
                "geval_success": bool(te.correctness_metric.success),
                "geval_reason": te.correctness_metric.reason,
                "geval_cost": te.correctness_metric.evaluation_cost,
                "latency": latency,
                "must_visit_success": bool(must_visit_metric.success),
                "must_visit_reason": must_visit_metric.reason,
            }
        )

    n = len(results)
    geval_pass = sum(r["geval_success"] for r in results)
    hybrid_pass = sum(r["geval_success"] and r["must_visit_success"] for r in results)
    avg_latency = sum(r["latency"] for r in results) / n
    costs = [r["geval_cost"] for r in results if r["geval_cost"] is not None]
    total_cost = sum(costs) if costs else None

    print(f"\n=== {args.variant.upper()} sweep ({n} cases) ===")
    for r in results:
        print(
            f"- {r['id']}: GEval={r['geval_score']:.2f} ({'PASS' if r['geval_success'] else 'FAIL'}), "
            f"MustVisit={'PASS' if r['must_visit_success'] else 'FAIL'}"
        )
        if not r["geval_success"]:
            print(f"    GEval reason: {r['geval_reason']}")
        if not r["must_visit_success"]:
            print(f"    MustVisit reason: {r['must_visit_reason']}")

    print(f"\nGEval-only pass rate:  {geval_pass}/{n} = {100 * geval_pass / n:.1f}%")
    print(f"Hybrid pass rate:      {hybrid_pass}/{n} = {100 * hybrid_pass / n:.1f}%")
    print(f"Avg latency (GEval call): {avg_latency:.2f}s")
    if total_cost is not None:
        print(f"Judge cost ({n} calls): ${total_cost:.4f}  ->  ${1000 * total_cost / n:.2f} / 1k queries")
    else:
        print("Judge cost: n/a (current judge model doesn't report per-call cost)")


if __name__ == "__main__":
    main()
