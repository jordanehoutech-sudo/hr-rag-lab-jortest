"""Authenticated real API evaluations; every case and repetition must complete."""
import json
import os
import time
from pathlib import Path
import requests
from auth import token_for

ROOT = Path(__file__).resolve().parents[1]

def check(case, answer, sources):
    normalize = lambda text: text.lower().replace(',', '').replace('$', '').replace('*', '')
    text = normalize(answer)
    issues = [f'missing:{fact}' for fact in case.get('must_include', []) if normalize(fact) not in text]
    issues += [f'forbidden:{fact}' for fact in case.get('must_not_include', []) if normalize(fact) in text]
    if case.get('source') and not any(s.startswith(case['source'] + ',') for s in sources):
        issues.append('missing_source')
    return issues

def request(session, origin, token, question, release, conversation=None):
    start = time.monotonic()
    response = session.post(origin + '/api/chat',
        headers={'Authorization': f'Bearer {token}'},
        json={'question': question, 'conversation_id': conversation}, timeout=35,
        allow_redirects=False)
    response.raise_for_status()
    if response.status_code != 200:
        raise ValueError('Unexpected API status')
    for key, value in [('x-hr-commit', release['commit']),
                       ('x-hr-prompt-sha256', release['prompt_sha256']),
                       ('x-hr-prompt-version', str(release['prompt_version'])),
                       ('x-hr-lambda-version', str(release['lambda_version']))]:
        if response.headers.get(key) != value:
            raise ValueError('API is not serving the expected release')
    body = response.json()
    if not isinstance(body.get('answer'), str) or not body['answer'].strip():
        raise ValueError('Missing answer')
    if not isinstance(body.get('sources'), list):
        raise ValueError('Missing sources')
    return body, time.monotonic() - start

def run():
    origin = os.environ['HR_STAGING_ORIGIN'].rstrip('/')
    if not origin.startswith('https://'):
        raise ValueError('HTTPS required')
    release = json.loads((ROOT / 'build/release.json').read_text())
    cases = json.loads((ROOT / 'lambda/data/evaluation_questions.json').read_text())
    repeats = int(os.getenv('EVAL_REPEATS', '2'))
    if not 1 <= repeats <= 5 or not cases:
        raise ValueError('Invalid evaluation size')
    records = []
    session = requests.Session()
    # This also checks that the API actually requires authentication.
    denied = session.post(origin + '/api/chat', json={'question': 'What is my salary?'},
                          timeout=35, allow_redirects=False)
    if denied.status_code not in (401, 403):
        raise ValueError('Unauthenticated request was not denied')
    for index, case in enumerate(cases):
        for repeat in range(repeats):
            record = {'case_id': str(index), 'repeat': repeat, 'passed': False}
            try:
                conversation = None
                for turn in case.get('history', []):
                    if turn['role'] == 'user':
                        body, _ = request(session, origin, token_for(case['email']), turn['content'],
                                          release, conversation)
                        conversation = body['conversation_id']
                body, latency = request(session, origin, token_for(case['email']),
                                         case['question'], release, conversation)
                problems = check(case, body['answer'], body['sources'])
                record.update(passed=not problems, problems=problems, latency_seconds=latency,
                              answer=body['answer'], sources=body['sources'])
            except Exception as error:
                # Do not include exception text that could contain tokens or HR response data.
                record['error'] = type(error).__name__
            records.append(record)
    result = {'release': release, 'expected': len(cases) * repeats, 'records': records}
    (ROOT / 'build/evaluation.json').write_text(json.dumps(result, indent=2))
    if len(records) != result['expected'] or any(not r['passed'] for r in records):
        raise SystemExit('Evaluation gate failed; inspect the restricted report')

if __name__ == '__main__':
    run()
