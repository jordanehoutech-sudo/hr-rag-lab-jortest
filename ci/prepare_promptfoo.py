"""Generate Promptfoo cases from approved references; no second model answer is generated."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
cases = json.loads((root/'lambda/data/evaluation_questions.json').read_text())
config = {'prompts':['{{question}}'],
    'providers':[{'id':'file://promptfoo-provider.cjs'}], 'tests':[]}
for i, case in enumerate(cases):
    config['tests'].append({'vars':{'case_id':str(i),'question':case['question'], 'reference':case},
        'assert':[{'type':'javascript',
            'value':"(()=>{ const rows=JSON.parse(output); const c=context.vars.reference; const norm=s=>String(s).toLowerCase().replace(/[,$*]/g,''); return rows.length>0 && rows.every(r=>!r.error && typeof r.answer==='string' && (c.must_include||[]).every(f=>norm(r.answer).includes(norm(f))) && (c.must_not_include||[]).every(f=>!norm(r.answer).includes(norm(f))) && (!c.source || (r.sources||[]).some(s=>s.startsWith(c.source+',')))); })()"}]})
(root/'ci/promptfoo.generated.json').write_text(json.dumps(config,indent=2))
