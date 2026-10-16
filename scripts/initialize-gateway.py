"""Wait for automatic LiteLLM initialization; do not print keys."""
import json, subprocess, time
import boto3
outputs=json.loads(subprocess.check_output(['terraform','-chdir=infra/terraform','output','-json'],text=True))
secret=outputs['gateway_app_key_secret_arn']['value']
client=boto3.client('secretsmanager')
for attempt in range(180):
    try:
        key=json.loads(client.get_secret_value(SecretId=secret)['SecretString'])['key']
        if key.startswith('sk-'):
            print('LiteLLM scoped application key initialized')
            break
    except client.exceptions.ResourceNotFoundException:pass
    time.sleep(10)
else:raise SystemExit('Gateway initialization failed; inspect the instance bootstrap logs without sharing secret files')
