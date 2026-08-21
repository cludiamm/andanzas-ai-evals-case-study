"""Generate data/optimized_outputs.json using the optimized system prompt.

Calls Anthropic once per golden_dataset.json case, with
prompts/system_prompt_v2.md as the system message and a user message built
from the case's input_user_request PLUS its constraints (must-visit anchor,
museum cap, and the specific_hard_bounds list -- ticket times, confirmation
numbers, closing days). Those constraints are what expected_output_ground_truth
was itself built from, so leaving them out isn't a fair test of the prompt:
early runs without them made the model correctly refuse to invent facts like
the exact Sintra date range, rather than producing an itinerary at all. This
is the "optimized" fixture set that evals/test_eval.py reads when
ITINERARY_VARIANT=optimized.

Resumable: an existing entry in optimized_outputs.json is left untouched
unless --force is passed, and the file is saved after every case (not just
at the end) -- so a run that fails partway (credits exhausted, network
error) can be re-run later and will only fill in what's missing. Any case
that never gets an automated result can also be filled in by hand: open
prompts/system_prompt_v2.md, paste it as the system prompt in your tool of
choice alongside the case's input_user_request, and add the resulting text
to optimized_outputs.json under that case's test_case_id -- same shape as
data/actual_outputs.json.

Usage:
    venv\\Scripts\\python.exe scripts\\generate_optimized_outputs.py
    venv\\Scripts\\python.exe scripts\\generate_optimized_outputs.py --force
    venv\\Scripts\\python.exe scripts\\generate_optimized_outputs.py --case trip_02_europa_solo_iberia_uk
"""
import argparse
import json
import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DATASET_PATH = ROOT / "data" / "golden_dataset.json"
OUTPUTS_PATH = ROOT / "data" / "optimized_outputs.json"
SYSTEM_PROMPT_PATH = ROOT / "prompts" / "system_prompt_v2.md"

# Pinned like the judge model (see evals/test_eval.py) so a re-run isn't
# comparing today's generation against a different model's behavior later.
# Independent of JUDGE_PROVIDER -- generation and judging deliberately use
# separate providers here to avoid competing for the same daily quota.
MODEL = os.getenv("GENERATOR_MODEL", "claude-opus-4-8")
MAX_TOKENS = 8192
COST_PER_INPUT_TOKEN = 5 / 1_000_000
COST_PER_OUTPUT_TOKEN = 25 / 1_000_000


def load_json(path: Path):
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_outputs(outputs: dict) -> None:
    with open(OUTPUTS_PATH, "w", encoding="utf-8") as f:
        json.dump(outputs, f, ensure_ascii=False, indent=2)
        f.write("\n")


def build_user_message(case: dict) -> str:
    constraints = case["constraints"]
    lines = [
        case["input_user_request"],
        "",
        "Already-confirmed logistics (locked facts -- schedule around these, do not ask about or second-guess them):",
        f"- Must-visit anchor: {constraints['must_visit_location']}",
        f"- Max paid museums/interiors per day: {constraints['max_museums_per_day']}",
    ]
    lines.extend(f"- {bound}" for bound in constraints.get("specific_hard_bounds", []))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Regenerate cases that already have an entry")
    parser.add_argument("--case", action="append", dest="cases", help="Only generate this test_case_id (repeatable)")
    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("Missing ANTHROPIC_API_KEY. Add it to your .env file before running this script.")

    system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    golden_dataset = load_json(DATASET_PATH)
    outputs = load_json(OUTPUTS_PATH)

    client = anthropic.Anthropic(api_key=api_key)
    target_ids = set(args.cases) if args.cases else None

    total_cost = 0.0
    for case in golden_dataset:
        test_case_id = case["test_case_id"]
        if target_ids and test_case_id not in target_ids:
            continue
        if test_case_id in outputs and not args.force:
            print(f"[skip] {test_case_id} already has an output (use --force to regenerate)")
            continue

        print(f"[generating] {test_case_id} ...")
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": build_user_message(case)}],
            )
            text = "".join(block.text for block in response.content if block.type == "text")
            outputs[test_case_id] = text
            save_outputs(outputs)  # persist after every case so partial progress survives a later failure

            case_cost = (
                response.usage.input_tokens * COST_PER_INPUT_TOKEN
                + response.usage.output_tokens * COST_PER_OUTPUT_TOKEN
            )
            total_cost += case_cost
            print(
                f"[done] {test_case_id} ({len(text)} chars, "
                f"{response.usage.input_tokens} in / {response.usage.output_tokens} out tokens, "
                f"${case_cost:.4f})"
            )
        except Exception as exc:
            print(f"[FAILED] {test_case_id}: {exc}")
            print(
                "  -> left out of optimized_outputs.json; fill it in manually later "
                "(see the module docstring for how)."
            )

    print(f"\nWrote {OUTPUTS_PATH} -- total spend this run: ${total_cost:.4f}")


if __name__ == "__main__":
    main()
