"""Hosted dataset pattern using the same captured real API responses, not fake answers."""
import json
import os
from pathlib import Path
from langfuse import Evaluation, RegressionError, get_client

ROOT = Path(__file__).resolve().parents[1]

def publish(context=None):
    report = json.loads(Path(os.getenv('HR_EVALUATION_REPORT', str(ROOT/'build/evaluation.json'))).read_text())
    cases = json.loads((ROOT/'lambda/data/evaluation_questions.json').read_text())
    rows = report['records']
    if len(rows) != report['expected']:
        raise ValueError('Incomplete real application records')
    lf = get_client()
    name = 'hr-regression-' + report['release']['dataset_sha256'][:16]
    lf.create_dataset(name=name, description='Approved synthetic Northwind regression cases')
    for i, case in enumerate(cases):
        lf.create_dataset_item(dataset_name=name, id=f'{name}-{i}',
            input={'case_id':str(i), 'question':case['question']},
            expected_output={k:case[k] for k in ('must_include','must_not_include','source') if k in case})
    dataset = lf.get_dataset(name)
    if len(dataset.items) != len(cases):
        raise ValueError('Hosted dataset coverage mismatch')
    # Frozen dataset name contains its content digest; verify the fetched definitions too.
    for item in dataset.items:
        case = cases[int(item.input['case_id'])]
        expected = {k:case[k] for k in ('must_include','must_not_include','source') if k in case}
        if item.input['question'] != case['question'] or item.expected_output != expected:
            raise ValueError('Hosted dataset changed after publication')
    def task(*, item, **kwargs):
        matches = [r for r in rows if r['case_id'] == item.input['case_id']]
        if not matches or any('answer' not in r for r in matches):
            raise ValueError('Missing real API output')
        return {'answers':[r['answer'] for r in matches],
                'passed_all_repeats':all(r['passed'] for r in matches)}
    def evaluator(*, output, **kwargs):
        return Evaluation(name='reference_checks', value=int(output['passed_all_repeats']))
    runner = dataset.run_experiment if context is None else context.run_experiment
    dataset_arguments = {} if context is None else {'data': dataset.items}
    result = runner(**dataset_arguments, name='HR API candidate',
        run_name=f"{report['release']['commit']}-{os.environ['GITHUB_RUN_ID']}",
        description='Evaluation of captured authenticated API outputs; task replays those outputs',
        task=task, evaluators=[evaluator], max_concurrency=2, metadata=report['release'])
    lf.flush()
    if len(result.item_results) != len(cases):
        raise ValueError('Experiment did not complete every required case')
    if any(not r.output or not r.output['passed_all_repeats'] for r in result.item_results):
        if context is not None:
            raise RegressionError(result=result)
        raise SystemExit('Langfuse experiment gate failed')
    # URLs and individual results stay in restricted artifacts; publish only safe counts to PRs.
    print(f'Langfuse experiment completed: {len(result.item_results)} cases')

    return result

def experiment(context):
    """Entry point used by the official Langfuse GitHub Action."""
    return publish(context)

if __name__ == '__main__':
    publish()
