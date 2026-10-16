"""Bedrock-shaped requests through LiteLLM. No direct-model fallback."""
import json
import os
from functools import cache
from urllib.parse import urlparse
import boto3
import requests

class GatewayPolicyDenied(RuntimeError):
    """Authorization, budget or rate-limit denial; never retry on another model."""

class GatewayUnavailable(RuntimeError):
    """Network/provider failure; another allowed model may be tried on the same key."""

@cache
def gateway_key():
    arn = os.environ['LLM_GATEWAY_KEY_SECRET_ARN']
    value = boto3.client('secretsmanager').get_secret_value(SecretId=arn)
    key = json.loads(value['SecretString'])['key']
    if not key or not key.startswith('sk-'):
        raise ValueError('Gateway key is not initialized')
    return key

class GatewayClient:
    def __init__(self, timeout=20):
        self.base = os.environ['LLM_GATEWAY_URL'].rstrip('/')
        parsed = urlparse(self.base)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username:
            raise ValueError('Invalid gateway endpoint')
        self.timeout = timeout

    def converse(self, modelId, **request):
        allowed = {os.environ['CHAT_MODEL'], os.environ['INLINE_JUDGE_MODEL']}
        fallback = os.getenv('FALLBACK_CHAT_MODEL')
        if fallback: allowed.add(fallback)
        if modelId not in allowed:
            raise GatewayPolicyDenied('Model is not approved for this application')
        config = request.get('inferenceConfig', {})
        if not 1 <= config.get('maxTokens', 1024) <= 2048:
            raise GatewayPolicyDenied('Output token limit exceeded')
        messages = []
        if request.get('system'):
            messages.append({'role':'system','content':'\n'.join(x['text'] for x in request['system'])})
        for message in request.get('messages', []):
            text=[];calls=[];results=[]
            for block in message.get('content', []):
                if 'text' in block: text.append(block['text'])
                elif 'toolUse' in block:
                    tool=block['toolUse']
                    calls.append({'id':tool['toolUseId'],'type':'function','function':{'name':tool['name'],'arguments':json.dumps(tool['input'])}})
                elif 'toolResult' in block:
                    tool=block['toolResult']
                    results.append({'role':'tool','tool_call_id':tool['toolUseId'],'content':json.dumps(tool['content'])})
                else: raise GatewayPolicyDenied('Unsupported content block')
            if text or calls:
                entry={'role':message['role'],'content':'\n'.join(text)}
                if calls: entry['tool_calls']=calls
                messages.append(entry)
            messages.extend(results)
        payload={'model':modelId,'messages':messages,'max_tokens':config.get('maxTokens',1024),'temperature':config.get('temperature',0)}
        tools=request.get('toolConfig',{}).get('tools',[])
        if tools:
            payload['tools']=[{'type':'function','function':{'name':t['toolSpec']['name'],'description':t['toolSpec'].get('description',''),'parameters':t['toolSpec']['inputSchema']['json']}} for t in tools]
        choice=request.get('toolConfig',{}).get('toolChoice',{})
        if 'any' in choice: payload['tool_choice']='required'
        elif 'tool' in choice: payload['tool_choice']={'type':'function','function':{'name':choice['tool']['name']}}
        try:
            response = requests.post(
                self.base + '/chat/completions',
                headers={'Authorization': 'Bearer ' + gateway_key()},
                json=payload, timeout=(2, self.timeout))
        except requests.RequestException as error:
            raise GatewayUnavailable('Gateway request did not complete') from error
        if response.status_code in (400, 401, 403, 429):
            # Do not expose proxy error bodies: they can contain keys or input text.
            raise GatewayPolicyDenied('Gateway rejected the request or its allowance')
        if response.status_code >= 500:
            raise GatewayUnavailable('Gateway or model service unavailable')
        if response.status_code != 200:
            raise GatewayPolicyDenied('Unexpected gateway response')
        value = response.json()
        choices=value.get('choices',[])
        if not choices: raise GatewayUnavailable('Incomplete gateway model response')
        message=choices[0]['message'];content=[]
        if message.get('content'): content.append({'text':message['content']})
        for call in message.get('tool_calls',[]):
            content.append({'toolUse':{'toolUseId':call['id'],'name':call['function']['name'],'input':json.loads(call['function']['arguments'])}})
        reason={'stop':'end_turn','tool_calls':'tool_use','length':'max_tokens'}.get(choices[0].get('finish_reason'),'unknown')
        usage=value.get('usage',{})
        return {'output':{'message':{'role':'assistant','content':content}},'stopReason':reason,
                'usage':{'inputTokens':usage.get('prompt_tokens',0),'outputTokens':usage.get('completion_tokens',0)}}
