"""Paired case bootstrap: repeated generations stay grouped by case."""
import json,os,random,statistics
from pathlib import Path
root=Path(__file__).resolve().parents[2]
def group(path):
    report=json.loads(Path(path).read_text());rows=report['records']
    if len(rows)!=report['expected'] or not rows:raise ValueError('Incomplete experiment')
    result={}
    for row in rows:result.setdefault(row['case_id'],[]).append(row)
    return result
baseline=group(os.environ['HR_BASELINE_REPORT']);candidate=group(root/'build/evaluation.json')
if baseline.keys()!=candidate.keys():raise ValueError('Baseline/candidate cases differ')
deltas=[]
for case in sorted(baseline):
    if len(baseline[case])!=len(candidate[case]):raise ValueError('Repeat counts differ')
    deltas.append(int(all(r['passed'] for r in candidate[case]))-int(all(r['passed'] for r in baseline[case])))
if len(deltas)<10:raise ValueError('Version comparison needs at least ten paired cases')
rng=random.Random(2026); samples=sorted(statistics.mean(rng.choices(deltas,k=len(deltas))) for _ in range(5000))
result={'paired_cases':len(deltas),'pass_rate_difference':statistics.mean(deltas),'illustrative_95_interval':[samples[125],samples[4874]],'note':'Fixed synthetic case resampling; not a production guarantee or a power analysis'}
(root/'build/comparison.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
