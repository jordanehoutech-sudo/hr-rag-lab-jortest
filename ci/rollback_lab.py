"""Restore the recorded prior approved alias; never destroys infrastructure."""
import json,os
from pathlib import Path
import boto3
root=Path(__file__).resolve().parents[1];previous=json.loads((root/'build/previous-approved.json').read_text());function=os.environ['HR_STAGING_FUNCTION']
if previous['function']!=function or not str(previous['version']).isdigit():raise SystemExit('Rollback target mismatch')
c=boto3.client('lambda');config=c.get_function_configuration(FunctionName=function,Qualifier=previous['version'])
if config.get('Environment',{}).get('Variables',{}).get('LAB_ENVIRONMENT')!='staging':raise SystemExit('Not isolated staging')
a=c.get_alias(FunctionName=function,Name='approved');c.update_alias(FunctionName=function,Name='approved',FunctionVersion=str(previous['version']),RevisionId=a['RevisionId'])
print('Prior lab approved version restored; verify readiness and quality after rollback')
