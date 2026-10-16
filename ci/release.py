"""Validate, publish a candidate prompt, and package its exact release identity."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from string import Formatter
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def digest(value):
    return hashlib.sha256(value).hexdigest()

def validate_prompt(text):
    fields = {field for _, field, _, _ in Formatter().parse(text) if field}
    if fields != {'full_name', 'job_title', 'department'}:
        raise ValueError(f'Unexpected prompt variables: {sorted(fields)}')
    if not text.strip() or len(text) > 30000:
        raise ValueError('Empty or oversized prompt')
    # Structural checks are not proof of resistance to prompt injection.
    text.format(full_name='Synthetic User', job_title='Employee', department='Demo')

def package(publish=False, output_dir=None):
    text = (ROOT / 'lambda/app/prompts/hr_system.txt').read_text(encoding='utf-8')
    validate_prompt(text)
    version = None
    if publish:
        from langfuse import get_client
        lf = get_client()
        prompt = lf.create_prompt(name='hr-policy-system', prompt=text, type='text',
            labels=['candidate'], config={'commit': os.environ['GITHUB_SHA'],
                'prompt_sha256': digest(text.encode())})
        version = prompt.version
        if lf.get_prompt('hr-policy-system', version=version).prompt != text:
            raise ValueError('Published prompt read-back mismatch')
    release = {'commit': os.getenv('GITHUB_SHA', 'development'),
        'prompt_sha256': digest(text.encode()), 'prompt_version': version,
        'dataset_sha256': digest((ROOT / 'lambda/data/evaluation_questions.json').read_bytes())}
    target = Path(output_dir) if output_dir is not None else ROOT / 'build'
    target.mkdir(exist_ok=True)
    with zipfile.ZipFile(target / 'function.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for source, prefix in [('lambda/app', 'app'), ('lambda/db', 'db')]:
            for path in sorted((ROOT / source).rglob('*')):
                if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc', '.pyo'):
                    inside = (Path(prefix) / path.relative_to(ROOT / source)).as_posix()
                    if inside == 'app/prompts/hr_system.txt':
                        archive.writestr(inside, text.encode('utf-8'))
                    else:
                        archive.write(path, inside)
        archive.write(ROOT / 'lambda/data/evaluation_questions.json', 'data/evaluation_questions.json')
        archive.write(ROOT / 'lambda/data/documents/manifest.json', 'data/policy_manifest.json')
        archive.writestr('app/release.json', json.dumps(release))
    release['artifact_sha256'] = digest((target / 'function.zip').read_bytes())
    (target / 'release.json').write_text(json.dumps(release, indent=2))
    return release

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    print(json.dumps(package(args.publish)))
