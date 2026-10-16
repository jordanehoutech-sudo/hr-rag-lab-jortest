import contextlib,io,json,os,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'lambda'))
from app.telemetry import observed,redact,conversation_context
class TelemetryTests(unittest.TestCase):
    def test_nested_spans_share_trace_and_hide_arguments(self):
        @observed('tool','tool')
        def tool(name,secret):return 'sensitive-output'
        @observed('request','agent')
        def root():return tool('lookup','private-token')
        stream=io.StringIO()
        with patch.dict(os.environ,{'HR_TRACING_ENABLED':'true'}),contextlib.redirect_stdout(stream):root()
        rows=[json.loads(line)['span'] for line in stream.getvalue().splitlines()]
        self.assertEqual(rows[0]['traceId'],rows[1]['traceId'])
        self.assertEqual(rows[0]['parentSpanId'],rows[1]['spanId'])
        self.assertNotIn('private-token',stream.getvalue())
        self.assertNotIn('sensitive-output',stream.getvalue())
    def test_exception_trace_does_not_copy_error_text(self):
        @observed('fails')
        def fail():raise ValueError('private-token')
        stream=io.StringIO()
        with patch.dict(os.environ,{'HR_TRACING_ENABLED':'true'}),contextlib.redirect_stdout(stream),self.assertRaises(ValueError):fail()
        self.assertNotIn('private-token',stream.getvalue())
        self.assertEqual(json.loads(stream.getvalue())['span']['status']['code'],2)

    def test_common_credential_patterns_are_redacted(self):
        self.assertEqual(redact('Bearer abc.def.ghi'), '[REDACTED]')
        self.assertEqual(redact('sk-lf-example-secret'), '[REDACTED]')

    def test_conversation_groups_all_spans_and_resets_between_requests(self):
        @observed('child')
        def child():return 'ok'
        @observed('root')
        def root():return child()
        stream=io.StringIO()
        with patch.dict(os.environ,{'HR_TRACING_ENABLED':'true'}),contextlib.redirect_stdout(stream):
            with conversation_context('synthetic-employee',42):root();root()
            with conversation_context('other-employee',42):root()
            root()
        rows=[json.loads(line)['span'] for line in stream.getvalue().splitlines()]
        attrs=[{a['key']:a['value']['stringValue'] for a in row['attributes']} for row in rows]
        self.assertEqual(len({a['langfuse.session.id'] for a in attrs[:4]}),1)
        self.assertNotEqual(attrs[0]['langfuse.session.id'],attrs[4]['langfuse.session.id'])
        self.assertNotIn('langfuse.session.id',attrs[-1])
        self.assertNotIn('synthetic-employee',stream.getvalue())

    def test_generation_links_exact_numeric_prompt_version(self):
        @observed('model','generation')
        def model():return 'ok'
        stream=io.StringIO()
        identity={'x-hr-commit':'source-hash','x-hr-prompt-sha256':'prompt-hash','x-hr-prompt-version':'5'}
        with patch.dict(os.environ,{'HR_TRACING_ENABLED':'true'}),patch('app.telemetry.release_identity',return_value=identity),contextlib.redirect_stdout(stream):model()
        attrs={a['key']:a['value'] for a in json.loads(stream.getvalue())['span']['attributes']}
        self.assertEqual(attrs['langfuse.version']['stringValue'],'hr-policy-system v5')
        self.assertEqual(attrs['langfuse.observation.prompt.version'],{'intValue':'5'})
        self.assertEqual(attrs['langfuse.release']['stringValue'],'source-hash')
