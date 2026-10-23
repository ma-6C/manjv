"""Provider adapters and process-local credentials for text and image services."""
from __future__ import annotations
import base64
import hashlib
import io
import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

PRESETS = [
    {'id':'ark','name':'火山方舟','base':'https://ark.cn-beijing.volces.com/api/v3','protocol':'chat','console':'https://console.volcengine.com/ark','images':True},
    {'id':'deepseek','name':'DeepSeek 官方','base':'https://api.deepseek.com/v1','protocol':'chat','console':'https://platform.deepseek.com','images':False},
    {'id':'dashscope','name':'阿里云百炼 / 通义千问','base':'https://dashscope.aliyuncs.com/compatible-mode/v1','protocol':'chat','console':'https://bailian.console.aliyun.com','images':False},
    {'id':'kimi','name':'Kimi / Moonshot','base':'https://api.moonshot.cn/v1','protocol':'chat','console':'https://platform.moonshot.cn','images':False},
    {'id':'zhipu','name':'智谱 GLM','base':'https://open.bigmodel.cn/api/paas/v4','protocol':'chat','console':'https://open.bigmodel.cn','images':False},
    {'id':'siliconflow','name':'硅基流动','base':'https://api.siliconflow.cn/v1','protocol':'chat','console':'https://cloud.siliconflow.cn','images':False},
    {'id':'openrouter','name':'OpenRouter','base':'https://openrouter.ai/api/v1','protocol':'chat','console':'https://openrouter.ai/settings/keys','images':False},
    {'id':'openai','name':'OpenAI','base':'https://api.openai.com/v1','protocol':'responses','console':'https://platform.openai.com','images':True},
    {'id':'anthropic','name':'Anthropic / Claude','base':'https://api.anthropic.com/v1','protocol':'anthropic','console':'https://console.anthropic.com','images':False},
    {'id':'gemini','name':'Google Gemini','base':'https://generativelanguage.googleapis.com/v1beta','protocol':'gemini','console':'https://aistudio.google.com','images':True},
    {'id':'custom','name':'自定义兼容服务','base':'','protocol':'chat','console':'','images':True},
]
TEXT_PROTOCOLS = {'chat','responses','anthropic','gemini'}
IMAGE_PROTOCOLS = {'ark_images','openai_images','openai_edits','gemini_image'}
_KEYS = {}
_KEY_LOCK = threading.RLock()

class ProviderError(ValueError):
    def __init__(self,message,code='ProviderError',status=None):
        super().__init__(message)
        self.code=code
        self.status=status

def normalize_url(value):
    if not isinstance(value,str):raise ValueError('接口地址必须为字符串')
    value=value.strip().rstrip('/')
    parsed=urllib.parse.urlsplit(value)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('接口地址须为不含用户名、密码和查询参数的 HTTPS Base URL')
    return value

def connection(cfg,channel='text'):
    if cfg.get('_aiConnection',{}).get('channel')==channel:
        return cfg['_aiConnection']
    if channel not in ['text','image']:raise ValueError('AI用途无效')
    if channel=='text':
        return {'provider':cfg.get('textProvider','ark'),'protocol':cfg.get('textProtocol','chat'),
                'base':normalize_url(cfg['apiBase']),'model':cfg.get('textModel',''),
                'tier':cfg.get('arkServiceTier','default'),'thinking':cfg.get('textThinking','default')}
    return {'provider':cfg.get('imageProvider','ark'),'protocol':cfg.get('imageProtocol','ark_images'),
            'base':normalize_url(cfg.get('imageApiBase') or cfg['apiBase']),'model':cfg.get('imageModel',''),
            'size':cfg.get('imageSize','2K')}

def validate(cfg):
    for channel in ['text','image']:
        c=connection(cfg,channel)
        if c['provider'] not in {p['id'] for p in PRESETS}:raise ValueError('未知AI平台')
        if c['protocol'] not in (TEXT_PROTOCOLS if channel=='text' else IMAGE_PROTOCOLS):raise ValueError('AI接口协议无效')
        if not isinstance(c['model'],str) or len(c['model'])>200:raise ValueError('模型ID无效')
    if cfg.get('arkServiceTier','default') not in ['default','auto','fast','flex']:raise ValueError('方舟推理模式无效')
    if cfg.get('textThinking','default') not in ['default','disabled','enabled']:raise ValueError('思考模式无效')
    cfg['apiBase']=normalize_url(cfg['apiBase'])
    cfg['imageApiBase']=normalize_url(cfg.get('imageApiBase') or cfg['apiBase'])
    return cfg

def identity(c):
    # Bind a credential to a specific provider, protocol and endpoint. Switching models is safe.
    parts=[c['provider'],c['protocol'],c['base']]
    if c.get('id'):parts.append(c['id'])
    return hashlib.sha256(json.dumps(parts,ensure_ascii=True).encode()).hexdigest()

def set_key(cfg,channel,value):
    if not isinstance(value,str):raise ValueError('密钥必须为文本')
    value=value.strip()
    if value and (len(value)>4096 or any(ord(x)<33 for x in value)):
        raise ValueError('密钥包含空白、换行或格式异常')
    with _KEY_LOCK:
        key=(channel,identity(connection(cfg,channel)))
        if value:_KEYS[key]=value
        else:_KEYS.pop(key,None)

def get_key(cfg,channel):
    with _KEY_LOCK:return _KEYS.get((channel,identity(connection(cfg,channel))),'')

def copy_text_key_to_image(cfg):
    text,image=connection(cfg,'text'),connection(cfg,'image')
    if text['provider']!=image['provider'] or urllib.parse.urlsplit(text['base']).netloc!=urllib.parse.urlsplit(image['base']).netloc:
        raise ValueError('仅能将文字密钥复制给同平台、同域名的生图服务')
    key=get_key(cfg,'text')
    if not key:raise ValueError('当前文字服务尚未设置密钥')
    set_key(cfg,'image',key)

def key_status(cfg):return {'text':bool(get_key(cfg,'text')),'image':bool(get_key(cfg,'image'))}

def redact(text):
    text=str(text)
    with _KEY_LOCK:
        for value in _KEYS.values():
            if value:text=text.replace(value,'[已隐藏]')
    return text

def provider_error(status,body):
    try:
        data=json.loads(body);err=data.get('error',{})
        code=str(err.get('code') or err.get('type') or err.get('status') or data.get('code') or 'HTTPError')[:100]
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',code):code='HTTPError'
    except Exception:code='HTTPError'
    hints={
        'ModelNotOpen':'当前账号未开通该模型或推理模式。请在平台开通，或切换已开通的模式。',
        'AccountOverdueError':'账号余额或计费状态异常，请在服务平台检查。',
        'SetLimitExceeded':'账号调用额度或限额已达到上限。',
        'InvalidApiKey':'密钥无效，请检查是否属于当前平台。',
        'AuthenticationError':'鉴权失败，请核对当前平台及密钥。',
        'InvalidParameter':'模型不支持当前请求参数，请检查协议、尺寸与模式。',
    }
    default={400:'请求参数不兼容，请检查模型、协议和可选参数。',401:'密钥鉴权失败，请核对当前平台和密钥。',
        403:'当前账号没有调用权限，请检查授权或计费状态。',404:'模型或接口不存在，或账号尚未开通。',
        429:'请求限流或额度不足，请稍后重试并检查平台限额。'}
    message=hints.get(code) or default.get(status,'服务暂时不可用，请稍后重试。')
    # Never return third-party raw response bodies; they can echo credentials and account identifiers.
    return ProviderError(f'HTTP {status} · {code}：{message}',code,status)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise ProviderError('接口发生重定向。请填写最终 Base URL，避免将密钥发送到其他地址。','RedirectBlocked',code)

def request_json(url,payload=None,key='',protocol='chat',timeout=90,raw=None,content_type='application/json',extra_headers=None):
    headers={'Content-Type':content_type,'Accept':'application/json'}
    if protocol=='anthropic':headers.update({'x-api-key':key,'anthropic-version':'2023-06-01'})
    elif protocol.startswith('gemini'):headers['x-goog-api-key']=key
    elif key:headers['Authorization']='Bearer '+key
    if extra_headers:headers.update(extra_headers)
    data=raw if raw is not None else json.dumps(payload,ensure_ascii=False).encode() if payload is not None else None
    req=urllib.request.Request(url,data=data,headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=timeout) as response:
            body=response.read(40*1024*1024+1)
            if len(body)>40*1024*1024:raise ProviderError('服务返回体过大','ResponseTooLarge')
            try:result=json.loads(body)
            except ValueError:raise ProviderError('接口未返回JSON，请检查协议和地址','InvalidResponse')
            if not isinstance(result,dict):raise ProviderError('接口返回格式无效','InvalidResponse')
            return result
    except urllib.error.HTTPError as e:raise provider_error(e.code,e.read(65536)) from None
    except (urllib.error.URLError,TimeoutError,OSError):
        raise ProviderError('连接超时或网络、HTTPS证书异常；证书校验保持启用。','NetworkError') from None

def extract_text(response,protocol):
    try:
        if protocol=='chat':
            result=response['choices'][0]['message']['content']
            if isinstance(result,list):result=''.join(part.get('text','') for part in result if isinstance(part,dict))
        elif protocol=='responses':
            result=response.get('output_text') or ''.join(part.get('text','') for item in response.get('output',[])
                if item.get('type')=='message' for part in item.get('content',[]) if part.get('type')=='output_text')
        elif protocol=='anthropic':result=''.join(part.get('text','') for part in response.get('content',[]) if part.get('type')=='text')
        else:result=''.join(part.get('text','') for part in response['candidates'][0]['content']['parts'] if not part.get('thought'))
        if not isinstance(result,str) or not result.strip():raise ValueError()
        return result.strip()
    except (ValueError,KeyError,TypeError,IndexError):
        raise ProviderError('模型未返回可用正文，可能被截断、进入思考模式或被内容过滤；请检查模型和参数。','EmptyOutput')

def text_generate(cfg,system,user,max_tokens=1024):
    if cfg.get('aiConnections') and not cfg.get('_aiDirect'):
        from api_connections import routed
        return routed(cfg,'text',lambda selected:text_generate(selected,system,user,max_tokens))
    c=connection(cfg,'text');key=get_key(cfg,'text')
    if not key:raise ValueError('请先为当前文字平台设置本次会话密钥')
    if not c['model'].strip():raise ValueError('请填写文字模型ID')
    protocol=c['protocol'];base=c['base'];model=c['model'];started=time.monotonic()
    if protocol=='chat':
        url=base+'/chat/completions'
        payload={'model':model,'messages':[{'role':'system','content':system},{'role':'user','content':user}],'stream':False}
        payload['max_completion_tokens' if c['provider']=='openai' else 'max_tokens']=max_tokens
        if c['provider']=='ark':payload['service_tier']=c['tier']
        if c['provider'] in ['ark','deepseek'] and c['thinking']!='default':payload['thinking']={'type':c['thinking']}
        if c['provider']=='dashscope' and c['thinking']!='default':payload['enable_thinking']=c['thinking']=='enabled'
    elif protocol=='responses':
        url=base+'/responses';payload={'model':model,'instructions':system,'input':user,'max_output_tokens':max_tokens,'stream':False}
        if c['provider']=='ark':
            payload['service_tier']=c['tier']
            if c['thinking']=='disabled':payload['reasoning']={'effort':'minimal'}
    elif protocol=='anthropic':
        url=base+'/messages';payload={'model':model,'system':system,'messages':[{'role':'user','content':user}],'max_tokens':max_tokens}
    else:
        safe_model=urllib.parse.quote(model.removeprefix('models/'),safe='-._')
        url=base+'/models/'+safe_model+':generateContent'
        payload={'systemInstruction':{'parts':[{'text':system}]},'contents':[{'role':'user','parts':[{'text':user}]}],
                 'generationConfig':{'maxOutputTokens':max_tokens}}
    response=request_json(url,payload,key,protocol)
    text=extract_text(response,protocol)
    return {'text':text,'model':response.get('model') or response.get('modelVersion') or model,'provider':c['provider'],
            'protocol':protocol,'serviceTier':response.get('service_tier'),'seconds':round(time.monotonic()-started,3),
            'usage':response.get('usage') or response.get('usageMetadata') or {}}

def list_models(cfg,channel='text'):
    c=connection(cfg,channel);key=get_key(cfg,channel)
    if not key:raise ValueError('请先设置当前平台的会话密钥')
    protocol=c['protocol'];url=c['base']+'/models'
    data=request_json(url,None,key,protocol)
    items=data.get('data') or data.get('models') or []
    models=[]
    for item in items:
        if not isinstance(item,dict):continue
        model=item.get('id') or item.get('name')
        if isinstance(model,str):models.append(model.removeprefix('models/'))
    return sorted(set(models))[:500]

def multipart(fields,image_bytes):
    boundary='manju'+secrets.token_hex(12);parts=[]
    for name,value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="reference.png"\r\nContent-Type: image/png\r\n\r\n'.encode()+image_bytes+b'\r\n')
    parts.append(f'--{boundary}--\r\n'.encode())
    return b''.join(parts),'multipart/form-data; boundary='+boundary

def image_generate(cfg,prompt,reference):
    if cfg.get('aiConnections') and not cfg.get('_aiDirect'):
        from api_connections import routed
        return routed(cfg,'image',lambda selected:image_generate(selected,prompt,reference))
    c=connection(cfg,'image');key=get_key(cfg,'image')
    if not key:raise ValueError('请先为当前生图平台设置本次会话密钥')
    if not c['model']:raise ValueError('请填写支持生图的模型ID；文字模型不能替代生图模型')
    ref=io.BytesIO();reference=reference.copy();reference.thumbnail((1536,1536));reference.convert('RGB').save(ref,format='JPEG')
    data_url='data:image/jpeg;base64,'+base64.b64encode(ref.getvalue()).decode()
    protocol=c['protocol'];base=c['base'];model=c['model']
    if protocol=='gemini_image':
        url=base+'/models/'+urllib.parse.quote(model.removeprefix('models/'),safe='-._')+':generateContent'
        payload={'contents':[{'parts':[{'text':prompt},{'inlineData':{'mimeType':'image/jpeg','data':base64.b64encode(ref.getvalue()).decode()}}]}],
                 'generationConfig':{'responseModalities':['TEXT','IMAGE']}}
        result=request_json(url,payload,key,protocol,timeout=300)
        for candidate in result.get('candidates',[]):
            for part in candidate.get('content',{}).get('parts',[]):
                data=part.get('inlineData') or part.get('inline_data')
                if data and data.get('data'):return base64.b64decode(data['data'],validate=True)
        raise ProviderError('生图模型没有返回图片，请检查模型能力和内容限制。','NoImage')
    if protocol=='openai_edits':
        png=io.BytesIO();reference.convert('RGBA').save(png,format='PNG')
        fields={'model':model,'prompt':prompt,'size':c['size'],'n':'1'}
        raw,ctype=multipart(fields,png.getvalue())
        result=request_json(base+'/images/edits',None,key,protocol,timeout=300,raw=raw,content_type=ctype)
    else:
        payload={'model':model,'prompt':prompt,'size':c['size'],'n':1}
        if protocol=='ark_images':payload.update(image=data_url,response_format='b64_json',watermark=True)
        elif c['provider']!='openai':payload['response_format']='b64_json'
        result=request_json(base+'/images/generations',payload,key,protocol,timeout=300)
    try:
        data=result['data'][0]
        if data.get('b64_json'):return base64.b64decode(data['b64_json'],validate=True)
        url=data['url']
        if not url.startswith('https://'):raise ValueError()
        # Image download deliberately carries no API credentials.
        with urllib.request.urlopen(url,timeout=90) as r:raw=r.read(30*1024*1024+1)
        if len(raw)>30*1024*1024:raise ValueError()
        return raw
    except (KeyError,IndexError,ValueError):raise ProviderError('生图接口未返回可读取的图片。','NoImage')
