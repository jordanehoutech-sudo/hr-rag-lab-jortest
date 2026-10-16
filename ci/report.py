"""Public-safe quality report; never posts raw questions, answers, or employee names."""
import json
import math
from pathlib import Path

def wilson(passed, total):
    if total <= 0 or not 0 <= passed <= total:
        raise ValueError('Invalid counts')
    z = 1.96
    p = passed / total
    denom = 1 + z*z/total
    centre = (p + z*z/(2*total))/denom
    half = z * math.sqrt(p*(1-p)/total + z*z/(4*total*total))/denom
    return centre-half, centre+half

def summarize(data):
    rows = data['records']
    if len(rows) != data['expected'] or not rows:
        raise ValueError('Incomplete report')
    # Collapse correlated repetitions to cases. A case passes only if all its runs pass.
    grouped = {}
    for row in rows:
        grouped.setdefault(row['case_id'], []).append(row['passed'])
    passed = sum(all(runs) for runs in grouped.values())
    lo, hi = wilson(passed, len(grouped))
    heading = (f'## HR application evaluation\n\n'
        f'Cases passing every repetition: {passed}/{len(grouped)}.\n\n'
        f'Illustrative 95% Wilson interval: {lo:.1%}–{hi:.1%}. '
        'This assumes independent representative cases; this fixed regression set '
        'does not establish a production error rate.\n\n'
        f'Application requests recorded: {len(rows)}.\n\n')
    verdict = 'PASS' if all(r['passed'] for r in rows) else 'FAIL'
    return heading + f'Release gate: {verdict}.\n'

if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    report = summarize(json.loads((root / 'build/evaluation.json').read_text()))
    (root / 'build/report.md').write_text(report)
    print(report)
