"""Fresh synthetic-user tokens. Never use this helper with real employee credentials."""
import json,os,time
import boto3
_cache={}
def token_for(email):
    if os.getenv('HR_SYNTHETIC_TOKENS'):
        return json.loads(os.environ['HR_SYNTHETIC_TOKENS'])[email]
    cached=_cache.get(email)
    if cached and cached[0]>time.monotonic():return cached[1]
    region=os.getenv('AWS_REGION','us-east-1')
    secret=boto3.client('secretsmanager',region_name=region).get_secret_value(SecretId=os.environ['HR_TEST_USERS_SECRET_ARN'])
    users=json.loads(secret['SecretString'])
    result=boto3.client('cognito-idp',region_name=region).admin_initiate_auth(UserPoolId=os.environ['HR_COGNITO_POOL_ID'],ClientId=os.environ['HR_COGNITO_CLIENT_ID'],AuthFlow='ADMIN_USER_PASSWORD_AUTH',AuthParameters={'USERNAME':email,'PASSWORD':users[email]})
    auth=result.get('AuthenticationResult',{})
    if not auth.get('IdToken'):raise ValueError('Synthetic user requires unexpected challenge')
    _cache[email]=(time.monotonic()+max(1,auth.get('ExpiresIn',3600)-300),auth['IdToken'])
    return auth['IdToken']
