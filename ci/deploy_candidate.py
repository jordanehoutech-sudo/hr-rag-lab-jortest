"""Update the isolated lab chat Lambda, publish, then move its candidate alias."""
import json
import os
from pathlib import Path
import boto3
from release import digest

def deploy(client, function, artifact, manifest):
    if digest(artifact) != manifest['artifact_sha256']:
        raise ValueError('Candidate artifact hash mismatch')
    if manifest.get('commit') != os.environ['GITHUB_SHA']:
        raise ValueError('Candidate commit mismatch')
    config = client.get_function_configuration(FunctionName=function)
    if config.get('Environment', {}).get('Variables', {}).get('LAB_ENVIRONMENT') != 'staging':
        raise ValueError('Deployment requires explicitly marked isolated staging Lambda')
    result = client.update_function_code(FunctionName=function, ZipFile=artifact,
                                        RevisionId=config['RevisionId'], Publish=True)
    client.get_waiter('function_updated_v2').wait(FunctionName=function)
    version = result['Version']
    alias = client.get_alias(FunctionName=function, Name='candidate')
    client.update_alias(FunctionName=function, Name='candidate', FunctionVersion=version,
                        RevisionId=alias['RevisionId'])
    return version

if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / 'build/release.json').read_text())
    version = deploy(boto3.client('lambda'), os.environ['HR_STAGING_FUNCTION'],
                     (root / 'build/function.zip').read_bytes(), manifest)
    manifest['lambda_version'] = version
    (root / 'build/release.json').write_text(json.dumps(manifest, indent=2))
