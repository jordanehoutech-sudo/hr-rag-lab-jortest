"""Bounded OTLP records to CloudWatch; an external exporter owns network delivery."""
import contextvars, functools, json, os, time, uuid, re, hashlib
from contextlib import contextmanager
from app.prompt_registry import release_identity
_SECRET=re.compile(r"(?:sk-lf-[A-Za-z0-9-]+|AKIA[A-Z0-9]{16}|Bearer\s+[A-Za-z0-9._~-]+|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)", re.IGNORECASE)
def redact(value):
    return _SECRET.sub("[REDACTED]",str(value))
_current=contextvars.ContextVar('hr_trace',default=None)
_identity=contextvars.ContextVar('hr_trace_identity',default=None)

@contextmanager
def conversation_context(employee_id, conversation_id):
    # Stable opaque identifiers are still pseudonymous data, not anonymized data.
    namespace=os.getenv('AWS_LAMBDA_FUNCTION_NAME','hr-rag-lab')
    user=hashlib.sha256(f'{namespace}:user:{employee_id}'.encode()).hexdigest()[:24]
    session=hashlib.sha256(f'{namespace}:user:{employee_id}:chat:{conversation_id}'.encode()).hexdigest()[:24]
    token=_identity.set({'user':'hr-user-'+user,'session':'hr-chat-'+session})
    try:yield
    finally:_identity.reset(token)

def attribute(key,value):
    return {'key':key,'value':{'stringValue':str(value)}}
def observed(name,kind='span'):
    def decorate(fn):
        @functools.wraps(fn)
        def wrapped(*args,**kwargs):
            if os.getenv('HR_TRACING_ENABLED','false')!='true':
                return fn(*args,**kwargs)
            parent=_current.get()
            state={'trace':parent['trace'] if parent else uuid.uuid4().hex,'id':uuid.uuid4().hex[:16]}
            token=_current.set(state)
            start=time.time_ns()
            attrs=[attribute('langfuse.observation.type',kind),attribute('langfuse.environment','staging'),attribute('langfuse.trace.name','HR application request')]
            grouping=_identity.get()
            if grouping:
                attrs += [attribute('langfuse.user.id',grouping['user']),attribute('langfuse.session.id',grouping['session'])]
            identity=release_identity()
            prompt_version=identity['x-hr-prompt-version']
            readable='hr-policy-system v'+prompt_version if prompt_version.isdigit() else 'hr-policy-system unpublished'
            attrs += [attribute('langfuse.release',identity['x-hr-commit']),
                      attribute('langfuse.version',readable),
                      attribute('langfuse.observation.metadata.prompt_version',prompt_version),
                      attribute('langfuse.observation.metadata.release_stage','candidate'),
                      attribute('langfuse.observation.metadata.prompt_sha256',identity['x-hr-prompt-sha256'])]
            if kind=='generation' and prompt_version.isdigit():
                attrs += [attribute('langfuse.observation.prompt.name','hr-policy-system'),
                          {'key':'langfuse.observation.prompt.version','value':{'intValue':prompt_version}}]
            status={'code':1}
            try:
                result=fn(*args,**kwargs)
                if kind=='generation':
                    response=result[0] if isinstance(result,tuple) else None
                    if isinstance(response,dict):
                        attrs.append(attribute('langfuse.observation.usage_details',json.dumps({'input':response.get('usage',{}).get('inputTokens',0),'output':response.get('usage',{}).get('outputTokens',0)})))
                    if args and isinstance(args[0],str):
                        attrs.append(attribute('langfuse.observation.model.name',args[0]))
                if kind=='tool' and args:
                    attrs.append(attribute('langfuse.observation.metadata.tool',args[0]))
                    attrs.append(attribute('langfuse.observation.metadata.result_characters',len(str(result))))
                    if os.getenv('HR_TRACE_SYNTHETIC_CONTENT','false')=='true' and os.getenv('LAB_ENVIRONMENT')=='staging':
                        attrs.append(attribute('langfuse.observation.output',json.dumps({'result':redact(result)[:8000]})))
                # Content export requires an explicit synthetic-data switch; never capture tokens or identity claims.
                if name=='HR answer' and os.getenv('HR_TRACE_SYNTHETIC_CONTENT','false')=='true' and os.getenv('LAB_ENVIRONMENT')=='staging':
                    attrs += [attribute('langfuse.observation.input',json.dumps({'question':redact(args[0])[:4000]})),attribute('langfuse.observation.output',json.dumps({'answer':redact(result[0])[:8000]}))]
                return result
            except Exception as error:
                status={'code':2,'message':type(error).__name__}
                raise
            finally:
                _current.reset(token)
                span={'traceId':state['trace'],'spanId':state['id'],'name':name,'kind':1,'startTimeUnixNano':str(start),'endTimeUnixNano':str(time.time_ns()),'attributes':attrs,'status':status}
                if parent: span['parentSpanId']=parent['id']
                print(json.dumps({'trace_record':'hr_otel','hr_otel':True,'span':span},separators=(',',':')))
        return wrapped
    return decorate
