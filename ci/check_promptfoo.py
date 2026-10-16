import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
data = json.loads((root/'build/promptfoo.json').read_text())
stats = data.get('results',{}).get('stats',{})
expected = len(json.loads((root/'lambda/data/evaluation_questions.json').read_text()))
if stats.get('successes') != expected or stats.get('failures') != 0 or stats.get('errors') != 0:
    raise SystemExit('Promptfoo gate failed or lacks complete coverage')
