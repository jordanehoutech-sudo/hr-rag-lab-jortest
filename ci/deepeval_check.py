"""Small independent LLM-judge demonstration over captured authenticated API answers."""
import asyncio,json,os,re
from pathlib import Path
import boto3
from botocore.config import Config
from deepeval.metrics import GEval
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase, SingleTurnParams
class BedrockJudge(DeepEvalBaseLLM):
    def __init__(self):
        self.model_name=os.getenv('EVAL_JUDGE_MODEL','amazon.nova-pro-v1:0')
        super().__init__(model=self.model_name)
    def load_model(self):
        return boto3.client('lambda', region_name=os.getenv('AWS_REGION','us-east-1'),
                            config=Config(read_timeout=60,retries={'max_attempts':0}))
    def generate(self,prompt,schema=None):
        result=self.model.invoke(FunctionName=os.environ['HR_EVALUATION_FUNCTION'],
            Payload=json.dumps({'gateway_judge':{'model':self.model_name,
                'messages':[{'role':'user','content':[{'text':prompt}]}]}}).encode())
        if result.get('FunctionError'):
            raise RuntimeError('Gateway evaluation judge failed or reached its allowance')
        response=json.loads(result['Payload'].read())
        text=''.join(b['text'] for b in response['output']['message']['content'] if 'text' in b).strip()
        text=re.sub(r'<thinking>.*?</thinking>','',text,flags=re.DOTALL|re.IGNORECASE).strip()
        fence=re.fullmatch(r'```(?:json)?\s*(.*?)\s*```',text,flags=re.DOTALL|re.IGNORECASE)
        if fence:text=fence.group(1).strip()
        return schema.model_validate_json(text) if schema else text
    async def a_generate(self,prompt,schema=None):return await asyncio.to_thread(self.generate,prompt,schema)
    def get_model_name(self):return self.model_name

def main():
    root = Path(__file__).resolve().parents[1]
    report = json.loads((root / 'build/evaluation.json').read_text())
    cases = json.loads((root / 'lambda/data/evaluation_questions.json').read_text())
    limit = int(os.getenv('DEEPEVAL_DEMO_CASES', '3'))
    unique = {row['case_id']: row for row in report['records']}
    output = []
    for row in list(unique.values())[:limit]:
        if row.get('error') or not row.get('answer'):
            raise SystemExit('Missing captured answer')
        case = cases[int(row['case_id'])]
        reference = {key: case[key] for key in ('must_include', 'must_not_include', 'source') if key in case}
        metric = GEval(
            name='HR reference outcome',
            evaluation_steps=[
                'Compare actual output with the required facts and forbidden facts in expected output.',
                'An access refusal is correct when required by the reference, even if the user requested protected data.',
                'A correct policy correction may contradict a false user claim. Do not penalize that contradiction.',
                'Penalize missing required facts and disclosure of forbidden facts. Do not demand unrelated information.'
            ],
            evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.EXPECTED_OUTPUT],
            threshold=0.7, model=BedrockJudge(), async_mode=False,
        )
        metric.measure(LLMTestCase(input=case['question'], actual_output=row['answer'],
                                 expected_output=json.dumps(reference)))
        output.append({'case_id': row['case_id'], 'score': metric.score,
                       'passed': metric.is_successful()})
    (root / 'build/deepeval.json').write_text(json.dumps(output, indent=2))
    print('DeepEval reference rubric completed. Model scores still require calibration and human review.')
    if not output or any(not row['passed'] for row in output):
        raise SystemExit('DeepEval reference rubric threshold failed')

if __name__ == '__main__':
    main()
