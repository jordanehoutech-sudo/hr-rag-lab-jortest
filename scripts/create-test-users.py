"""Initialize synthetic lab users once; keep passwords in Secrets Manager, not terminal output."""
import json,os,secrets,subprocess
from pathlib import Path
import boto3
from botocore.exceptions import ClientError
root=Path(__file__).resolve().parents[1]
outputs=json.loads(subprocess.check_output(['terraform','-chdir=infra/terraform','output','-json'],cwd=root)); get=lambda name:outputs[name]['value']
region=os.getenv('AWS_REGION','us-east-1'); sm=boto3.client('secretsmanager',region_name=region); cp=boto3.client('cognito-idp',region_name=region)
try: users=json.loads(sm.get_secret_value(SecretId=get('evaluation_users_secret_arn'))['SecretString'])
except sm.exceptions.ResourceNotFoundException: users={}
emails=sorted({case['email'] for case in json.loads((root/'lambda/data/evaluation_questions.json').read_text())})
for email in emails:
    try:cp.admin_get_user(UserPoolId=get('cognito_user_pool_id'),Username=email)
    except cp.exceptions.UserNotFoundException:cp.admin_create_user(UserPoolId=get('cognito_user_pool_id'),Username=email,MessageAction='SUPPRESS',UserAttributes=[{'Name':'email','Value':email},{'Name':'email_verified','Value':'true'}])
    if email not in users:
        users[email]='Aa1!'+secrets.token_urlsafe(24)
    # Reapply the retained password after a user pool is recreated.
    cp.admin_set_user_password(UserPoolId=get('cognito_user_pool_id'),Username=email,Password=users[email],Permanent=True)
sm.put_secret_value(SecretId=get('evaluation_users_secret_arn'),SecretString=json.dumps(users))
print('Synthetic evaluation accounts initialized; passwords retained securely')
