#!/usr/bin/env python3
"""Generate deterministic D4 evidence without any external service."""
import argparse

from src.d4_evaluation import run_evaluation


def format_summary(result):
    """Format status truthfully for terminal output and automated tests."""
    prefix = (f"D4: {result['code_checks']['passed_trials']}/{result['trial_count']} code-scored trials; "
              f"model={result['model']}; prompt={result['prompt_version']}; "
              f"date={result['evaluation_date']}; status={result['final_status']}")
    if result["final_status"] == "pending_human_judgement":
        return prefix + "; final pass rate remains pending human judgement"
    if result["final_status"] == "complete":
        return prefix + f"; final pass rate={result['final_pass_rate']:.6f}"
    return prefix + "; evaluation failed"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluation-date", required=True,
                        help="Stable declared evaluation date (YYYY-MM-DD)")
    args = parser.parse_args()
    result = run_evaluation(evaluation_date=args.evaluation_date)
    print(format_summary(result))
