"""Prepare numeric proxy measurements; keep answer text out of the report input."""
import hashlib
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    current = json.loads((ROOT / 'build/evaluation.json').read_text())
    reference = json.loads((ROOT / 'ci/data/drift-reference.json').read_text())
    cases = json.loads((ROOT / 'lambda/data/evaluation_questions.json').read_text(encoding='utf-8'))
    canonical = json.dumps(cases, sort_keys=True, separators=(',', ':')).encode()
    if hashlib.sha256(canonical).hexdigest() != reference['case_definitions_sha256']:
        raise ValueError('Compare the same case dataset, or explicitly prepare a new reference')
    rows = []
    for record in current['records']:
        if record.get('answer') and not record.get('error'):
            rows.append({'answer_length': len(record['answer']),
                         'latency_seconds': record['latency_seconds']})
    if len(rows) < 10:
        raise ValueError('At least ten completed observations are required')
    with (ROOT / 'build/drift-current.csv').open('w', newline='', encoding='utf-8') as output:
        writer = csv.DictWriter(output, fieldnames=['answer_length', 'latency_seconds'])
        writer.writeheader()
        writer.writerows(rows)
    print('Proxy data ready. A shift requests investigation; it does not prove poor quality.')

if __name__ == '__main__':
    main()
