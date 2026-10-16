"""Compare independently recorded human grades with model grades.

The input CSV contains human_pass and judge_pass: 1 means pass, 0 means fail.
A domain expert supplies human grades; this script does not invent them.
"""

import csv
import json
import os
from pathlib import Path


def read_grade(value):
    if value not in ("0", "1"):
        raise ValueError("Each grade must be 0 or 1.")
    return int(value)


def main():
    # 1. Load the same cases graded separately by a human and a model.
    labels_file = Path(os.environ["HR_HUMAN_JUDGE_LABELS"])
    with labels_file.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    if len(rows) < 10:
        raise ValueError("Use at least ten labelled synthetic cases.")

    # 2. Count how often their grades match.
    matching_grades = 0
    human_passes = 0
    judge_passes = 0
    for row in rows:
        human_grade = read_grade(row["human_pass"])
        judge_grade = read_grade(row["judge_pass"])
        if human_grade == judge_grade:
            matching_grades += 1
        human_passes += human_grade
        judge_passes += judge_grade

    case_count = len(rows)
    agreement = matching_grades / case_count

    # 3. Kappa adjusts agreement for the agreement expected by chance.
    # If every label is identical, this adjustment is undefined: report None.
    human_pass_rate = human_passes / case_count
    judge_pass_rate = judge_passes / case_count
    expected_agreement = (
        human_pass_rate * judge_pass_rate
        + (1 - human_pass_rate) * (1 - judge_pass_rate)
    )
    kappa = None
    if expected_agreement != 1:
        kappa = (agreement - expected_agreement) / (1 - expected_agreement)

    # 4. Report the comparison. Agreement alone does not prove correctness.
    print(json.dumps({
        "cases": case_count,
        "raw_agreement": agreement,
        "cohens_kappa": kappa,
        "note": "Review disagreements with the domain expert; neither grader is automatically ground truth.",
    }, indent=2))


if __name__ == "__main__":
    main()
