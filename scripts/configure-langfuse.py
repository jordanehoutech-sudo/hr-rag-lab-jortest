"""Upload local key pair to the lab secret without displaying values or storing them in Terraform state."""
import json,os,subprocess
from pathlib import Path
import boto3
root=Path(__file__).resolve().parents[1]
values=dict(line.split('=',1) for line in (root/'.env.langfuse').read_text(encoding='utf-8-sig').splitlines() if '=' in line and not line.lstrip().startswith('#'))
values={k:v.strip().strip('"').strip("'") for k,v in values.items()}
if not values.get('LANGFUSE_PUBLIC_KEY','').startswith('pk-lf-') or not values.get('LANGFUSE_SECRET_KEY','').startswith('sk-lf-'):raise SystemExit('Check public/secret fields')
outputs=json.loads(subprocess.check_output(['terraform','-chdir=infra/terraform','output','-json'],cwd=root))
secret=outputs['langfuse_secret_arn']['value']
region=os.getenv('AWS_REGION','us-east-1')
boto3.client('secretsmanager',region_name=region).put_secret_value(SecretId=secret,SecretString=json.dumps({'public_key':values['LANGFUSE_PUBLIC_KEY'],'secret_key':values['LANGFUSE_SECRET_KEY']}))
print('Lab Langfuse key pair stored in Secrets Manager')
