# Additional evaluation examples

These examples are outside the main GitHub Actions delivery path. They are supplied for deeper analysis, not additional required pipeline stages.

| Example | Purpose | Input |
|---|---|---|
| `evidently_drift.py` | Alternative local report generation; the pipeline uses the Evidently Action instead | `HR_BASELINE_REPORT` and `build/evaluation.json` |
| `compare_versions.py` | Paired case comparison with an illustrative uncertainty interval | `HR_BASELINE_REPORT` and `build/evaluation.json` |
| `judge_agreement.py` | Compare independent human and model grades | `HR_HUMAN_JUDGE_LABELS`, a CSV with `human_pass` and `judge_pass` columns |

Run these from the repository root using `python examples/evaluation/FILE.py`, after providing their inputs and installing `ci/requirements-demo.txt`. Do not invent human labels or interpret proxy drift as proof of incorrect answers.
