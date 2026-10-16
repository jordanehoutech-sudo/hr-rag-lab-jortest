import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ci'))
sys.path.insert(0, str(ROOT / 'lambda'))
from release import validate_prompt, package
from report import wilson, summarize
from app.inline_judge import validate_answer, SAFE_REPLY, assess
from unittest.mock import patch

class ReleaseTests(unittest.TestCase):
    def test_real_prompt_parses(self):
        validate_prompt((ROOT/'lambda/app/prompts/hr_system.txt').read_text())

    def test_package_includes_the_approved_policy_manifest(self):
        import json, tempfile, zipfile
        with tempfile.TemporaryDirectory() as temporary:
            package(output_dir=temporary)
            with zipfile.ZipFile(pathlib.Path(temporary) / "function.zip") as archive:
                packaged = json.loads(archive.read("data/policy_manifest.json"))
            approved = json.loads((ROOT / "lambda/data/documents/manifest.json").read_text())
            self.assertEqual(packaged, approved)

    def test_extra_variable_rejected(self):
        with self.assertRaises(ValueError):
            validate_prompt('{full_name} {job_title} {department} {secret}')

    def test_package_contains_exact_prompt_and_identity(self):
        import json, zipfile, hashlib
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            manifest = package(output_dir=temporary)
            with zipfile.ZipFile(pathlib.Path(temporary)/'function.zip') as archive:
                prompt = archive.read('app/prompts/hr_system.txt')
                identity = json.loads(archive.read('app/release.json'))
        self.assertEqual(hashlib.sha256(prompt).hexdigest(), manifest['prompt_sha256'])
        self.assertEqual(identity['dataset_sha256'], manifest['dataset_sha256'])

    def test_judge_retries_once_and_falls_back(self):
        with patch.dict('os.environ', {'INLINE_JUDGE_ENABLED':'true', 'INLINE_JUDGE_MODEL':'test'}), \
             patch('app.inline_judge.assess', return_value={'pass':False,'reason':'unsupported'}) as judge, \
             patch('app.inline_judge.converse_text', return_value='revised') as revision:
            self.assertEqual(validate_answer('q','draft',[],{},object()), SAFE_REPLY)
            self.assertEqual(judge.call_count,2)
            self.assertEqual(revision.call_count,1)

    def test_judge_error_withholds_draft(self):
        with patch.dict('os.environ', {'INLINE_JUDGE_ENABLED':'true', 'INLINE_JUDGE_MODEL':'test'}), \
             patch('app.inline_judge.assess', side_effect=ValueError):
            self.assertEqual(validate_answer('q','draft',[],{},object()), SAFE_REPLY)

    def test_judge_pass_returns_draft(self):
        with patch.dict('os.environ', {'INLINE_JUDGE_ENABLED':'true', 'INLINE_JUDGE_MODEL':'test'}), \
             patch('app.inline_judge.assess', return_value={'pass':True,'reason':'supported'}):
            self.assertEqual(validate_answer('q','draft',[],{},object()),'draft')

    def test_repeated_runs_do_not_inflate_sample_size(self):
        report = summarize({'expected':2,'records':[{'case_id':'a','passed':True}]*2})
        self.assertIn('1/1', report)

    def test_missing_report_fails(self):
        with self.assertRaises(ValueError):
            summarize({'expected':2,'records':[]})

    def test_interval_not_zero_error_guarantee(self):
        self.assertLess(wilson(43,43)[0],1)

    def test_judge_does_not_start_with_insufficient_response_budget(self):
        with patch.dict('os.environ', {'INLINE_JUDGE_ENABLED':'true','INLINE_JUDGE_MODEL':'test'}), patch('app.inline_judge.assess') as judge:
            self.assertEqual(validate_answer('q','draft',[],{},object(),remaining_seconds=2),SAFE_REPLY)
            judge.assert_not_called()

    def test_judge_accepts_complete_fenced_json(self):
        raw='<thinking>provider formatting</thinking>\n```json\n{"pass":true,"reason":"supported"}\n```'
        with patch('app.inline_judge.converse_text',return_value=raw):
            self.assertTrue(assess(object(),'test','q','a',[])['pass'])

    def test_judge_accepts_single_line_fenced_json(self):
        with patch('app.inline_judge.converse_text',return_value='```json {"pass":true,"reason":"supported"}```'):
            self.assertTrue(assess(object(),'test','q','a',[])['pass'])

    def test_judge_rejects_extra_unstructured_verdict_text(self):
        with patch('app.inline_judge.converse_text',return_value='Probably fine {"pass":true,"reason":"supported"}'), self.assertRaises(ValueError):
            assess(object(),'test','q','a',[])

if __name__ == '__main__':
    unittest.main()

