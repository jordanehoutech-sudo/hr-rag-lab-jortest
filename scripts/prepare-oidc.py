"""Generate scoped lab IAM policies for review; do not change AWS resources."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def read_json(arguments):
    if arguments[0] == "aws":
        arguments = arguments + ["--output", "json", "--no-cli-pager"]
    return json.loads(subprocess.check_output(arguments, text=True, cwd=ROOT))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo')
    parser.add_argument('--region', default='us-east-1')
    parser.add_argument('--subject-prefix', help='Exact repository subject prefix copied from GitHub settings')
    args = parser.parse_args()
    args.repo = args.repo or input('Your GitHub repository (username/hr-rag-lab): ').strip()
    args.subject_prefix = args.subject_prefix or input('Exact OIDC subject prefix from GitHub settings: ').strip()
    owner, repo = args.repo.split('/')
    import re
    pattern = rf"repo:{re.escape(owner)}(?:@[0-9]+)?/{re.escape(repo)}(?:@[0-9]+)?"
    if not re.fullmatch(pattern, args.subject_prefix):
        raise SystemExit('Subject prefix must identify exactly this repository, with no wildcards or custom claims')
    outputs = read_json(['terraform', '-chdir=infra/terraform', 'output', '-json'])
    account = read_json(['aws', 'sts', 'get-caller-identity'])['Account']
    def value(name):
        return outputs[name]['value']
    secret = value('evaluation_users_secret_arn')
    if secret.split(':')[4] != account:
        raise SystemExit('Terraform outputs belong to a different AWS account')
    partition = secret.split(':')[1]
    function = f"arn:{partition}:lambda:{args.region}:{account}:function:{value('candidate_function')}"
    provider = f"arn:{partition}:iam::{account}:oidc-provider/token.actions.githubusercontent.com"
    trust = {'Version':'2012-10-17','Statement':[{'Effect':'Allow','Principal':{'Federated':provider},'Action':'sts:AssumeRoleWithWebIdentity','Condition':{'StringEquals':{'token.actions.githubusercontent.com:aud':'sts.amazonaws.com','token.actions.githubusercontent.com:sub':args.subject_prefix+':environment:hr-staging'}}}]}
    def allow(actions, resources):
        return {'Effect':'Allow','Action':actions,'Resource':resources}
    policy = {'Version':'2012-10-17','Statement':[
        allow(['lambda:GetFunction','lambda:GetFunctionConfiguration','lambda:UpdateFunctionCode','lambda:GetAlias','lambda:UpdateAlias','lambda:CreateAlias','lambda:PublishVersion'],[function,function+':*']),
        allow('secretsmanager:GetSecretValue',secret),
        allow('cognito-idp:AdminInitiateAuth',f"arn:{partition}:cognito-idp:{args.region}:{account}:userpool/{value('cognito_user_pool_id')}"),
        allow('s3:PutObject',f"arn:{partition}:s3:::{value('frontend_bucket')}/*"),
        allow('cloudfront:CreateInvalidation',f"arn:{partition}:cloudfront::{account}:distribution/{value('cloudfront_distribution_id')}"),
        allow('lambda:InvokeFunction',f"arn:{partition}:lambda:{args.region}:{account}:function:{value('evaluation_function')}"),
    ]}
    target = ROOT/'build'
    target.mkdir(exist_ok=True)
    (target/'github-oidc-trust.json').write_text(json.dumps(trust,indent=2),encoding='utf-8')
    (target/'github-oidc-permissions.json').write_text(json.dumps(policy,indent=2),encoding='utf-8')
    print('Generated two scoped IAM policy files in build. Review before creating the role.')

if __name__ == '__main__':
    main()
