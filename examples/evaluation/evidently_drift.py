"""Compare captured baseline/candidate proxy distributions; drift is a review signal."""
import json,os
from pathlib import Path
import pandas as pd
from evidently import Dataset,DataDefinition,Report
from evidently.presets import DataDriftPreset
root=Path(__file__).resolve().parents[2]
def dataset(path):
    records=json.loads(Path(path).read_text())['records']
    data=[{'answer_length':len(r['answer']),'latency_seconds':r['latency_seconds']} for r in records if r.get('answer') and not r.get('error')]
    if len(data)<10:raise ValueError('At least ten completed observations required')
    return Dataset.from_pandas(pd.DataFrame(data),data_definition=DataDefinition())
reference=dataset(os.environ['HR_BASELINE_REPORT']);current=dataset(root/'build/evaluation.json')
result=Report([DataDriftPreset()]).run(current,reference)
result.save_html(str(root/'build/drift.html'))
print('Evidently proxy drift report saved; inspect shifts, not proof of incorrect answers')
