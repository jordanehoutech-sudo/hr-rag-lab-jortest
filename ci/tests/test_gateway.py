import os, sys, unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'lambda'))
from app.model_gateway import GatewayClient, GatewayPolicyDenied, GatewayUnavailable

ENV={'LLM_GATEWAY_URL':'http://gateway:4000','CHAT_MODEL':'primary','INLINE_JUDGE_MODEL':'judge','FALLBACK_CHAT_MODEL':'fallback'}
class GatewayTests(unittest.TestCase):
    def response(self,status):
        response=Mock(status_code=status)
        response.json.return_value={'choices':[{'message':{'content':'ok'},'finish_reason':'stop'}],'usage':{'prompt_tokens':3,'completion_tokens':1}}
        return response
    def test_converse_preserves_native_tools_and_response(self):
        request={'messages':[{'role':'user','content':[{'text':'question'}]}], 'toolConfig':{'tools':[]},'inferenceConfig':{'maxTokens':100}}
        with patch.dict(os.environ,ENV),patch('app.model_gateway.gateway_key',return_value='sk-test'),patch('app.model_gateway.requests.post',return_value=self.response(200)) as call:
            result=GatewayClient().converse(modelId='primary',**request)
            self.assertEqual(call.call_args.kwargs['json']['messages'],[{'role':'user','content':'question'}])
            self.assertTrue(call.call_args.args[0].endswith('/chat/completions'))
            self.assertEqual(result['output']['message']['role'],'assistant')
    def test_budget_rate_and_auth_denials_are_not_transient(self):
        for status in (401,403,429):
            with self.subTest(status=status),patch.dict(os.environ,ENV),patch('app.model_gateway.gateway_key',return_value='sk-test'),patch('app.model_gateway.requests.post',return_value=self.response(status)) as call:
                with self.assertRaises(GatewayPolicyDenied):GatewayClient().converse(modelId='judge',messages=[])
                self.assertEqual(call.call_count,1)
    def test_unknown_model_and_oversize_output_are_rejected_before_network(self):
        with patch.dict(os.environ,ENV),patch('app.model_gateway.requests.post') as call:
            with self.assertRaises(GatewayPolicyDenied):GatewayClient().converse(modelId='unapproved',messages=[])
            with self.assertRaises(GatewayPolicyDenied):GatewayClient().converse(modelId='primary',inferenceConfig={'maxTokens':9999})
            call.assert_not_called()
    def test_no_endpoint_means_no_direct_bedrock_fallback(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(KeyError):GatewayClient()
    def test_transient_failure_is_distinct_from_policy_denial(self):
        with patch.dict(os.environ,ENV),patch('app.model_gateway.gateway_key',return_value='sk-test'),patch('app.model_gateway.requests.post',return_value=self.response(503)):
            with self.assertRaises(GatewayUnavailable):GatewayClient().converse(modelId='primary',messages=[])
