"""Asynchronous video generation adapters. A submitted task is never resubmitted on resume."""
from __future__ import annotations
import base64,io,re,time,urllib.parse,urllib.request
from pathlib import Path
import ai_providers as ai
import api_connections as routes

def validate_spec(raw):
    if not isinstance(raw,dict):raise ValueError('视频生成参数无效')
    spec={k:raw.get(k,v) for k,v in {'name':'AI视频','prompt':'','mode':'text','reference':'','duration':5,'ratio':'16:9','resolution':'720p'}.items()}
    for k in ['name','prompt','reference','mode','ratio','resolution']:
        if not isinstance(spec[k],str):raise ValueError('视频生成字段必须为文本')
    spec['name']=spec['name'].strip();spec['prompt']=spec['prompt'].strip()
    if not spec['name'] or len(spec['name'])>70 or not spec['prompt'] or len(spec['prompt'])>4000:raise ValueError('请填写作品名及不超过4000字的视频提示词')
    if spec['mode'] not in ['text','image'] or spec['ratio'] not in ['16:9','9:16','1:1','4:3','3:4']:raise ValueError('视频类型或画幅无效')
    if spec['resolution'] not in ['720p','1080p']:raise ValueError('请选择720p或1080p')
    if type(spec['duration']) is not int or not 2<=spec['duration']<=15:raise ValueError('视频时长须为2至15之间的整数秒，具体以模型能力为准')
    if spec['mode']=='image':
        value=spec['reference'].strip();spec['reference']=value
        if value.startswith('https://'):
            url=urllib.parse.urlsplit(value)
            if not url.hostname or url.username or url.password:raise ValueError('参考图URL无效')
        elif not Path(value).is_file() or Path(value).suffix.lower() not in ['.jpg','.jpeg','.png','.webp']:
            raise ValueError('图生视频请选择本地图片，或填写HTTPS图片地址')
    else:spec['reference']=''
    return spec

def image_url(spec):
    if spec['mode']!='image':return ''
    value=spec['reference']
    if value.startswith('https://'):return value
    from PIL import Image
    with Image.open(value) as im:
        im=im.convert('RGB');im.thumbnail((1920,1920));buf=io.BytesIO();im.save(buf,'JPEG',quality=90)
    return 'data:image/jpeg;base64,'+base64.b64encode(buf.getvalue()).decode()

def submit(cfg,c,spec):
    key=routes.require_key(cfg,c);base=c['base'];protocol=c['protocol'];reference=image_url(spec)
    if not c['model']:raise ai.ProviderError('请填写具备视频生成能力的模型ID','InvalidParameter')
    if protocol=='ark_video':
        content=[{'type':'text','text':spec['prompt']}]
        if reference:content.append({'type':'image_url','image_url':{'url':reference}})
        result=ai.request_json(base+'/contents/generations/tasks',{'model':c['model'],'content':content,
            'duration':spec['duration'],'ratio':spec['ratio'],'resolution':spec['resolution'],'watermark':True},key,timeout=90)
    elif protocol=='dashscope_video':
        inputs={'prompt':spec['prompt']}
        if reference:inputs['media']=[{'type':'first_frame','url':reference}]
        result=ai.request_json(base+'/services/aigc/video-generation/video-synthesis',{'model':c['model'],'input':inputs,
            'parameters':{'duration':spec['duration'],'ratio':spec['ratio'],'resolution':spec['resolution'].upper(),'watermark':True}},key,
            timeout=90,extra_headers={'X-DashScope-Async':'enable'})
    else:
        result=ai.request_json(base+c['submitPath'],{'model':c['model'],'prompt':spec['prompt'],'image_url':reference,
            'duration':spec['duration'],'ratio':spec['ratio'],'resolution':spec['resolution']},key,timeout=90)
    task_id=result.get('id') or result.get('task_id') or result.get('output',{}).get('task_id')
    if not isinstance(task_id,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}',task_id):
        raise ai.ProviderError('服务未返回可查询的任务ID；请在平台核对提交结果，本任务不会自动重复提交','SubmissionUnknown')
    return task_id

def poll(cfg,c,task_id):
    key=routes.require_key(cfg,c);token=urllib.parse.quote(task_id,safe='')
    path='/contents/generations/tasks/'+token if c['protocol']=='ark_video' else '/tasks/'+token if c['protocol']=='dashscope_video' else c['pollPath'].replace('{id}',token)
    result=ai.request_json(c['base']+path,None,key,timeout=60)
    data=result.get('output') or result
    status=str(data.get('task_status') or data.get('status') or '').lower()
    content=data.get('content') or {}
    url=content.get('video_url') or data.get('video_url') or ''
    if status in ['succeeded','completed','success']:
        parsed=urllib.parse.urlsplit(url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:raise ai.ProviderError('视频任务成功但没有HTTPS视频地址','InvalidResponse')
        return 'succeeded',url
    if status in ['failed','cancelled','canceled','expired']:
        raise ai.ProviderError('云端视频任务已失败、取消或过期，请在平台核对任务详情','RemoteTaskFailed')
    if status not in ['queued','pending','running','processing','submitted']:raise ai.ProviderError('云端任务返回未知状态','InvalidResponse')
    return status,''

def generate(cfg,spec,remote,record,cancel,progress):
    choices=routes.candidates(cfg,'video')
    if not choices:raise ValueError('请在接口管理中添加并选择视频生成连接')
    if remote and remote.get('taskId'):
        c=remote['connection'];task_id=remote['taskId']
        routes.require_key(cfg,c);routes.report(cfg,c,'resume','继续查询原云端任务 '+task_id)
    else:
        if remote and remote.get('status') in ['submitting','submission_unknown']:
            raise ai.ProviderError('上次提交结果未知。请在平台核对，可在任务卡片填入已有云端任务ID继续查询；本任务不会自动重发','SubmissionUnknown')
        for index,c in enumerate(choices):
            try:
                routes.require_key(cfg,c)
                if not c['model']:raise ai.ProviderError('请填写视频模型ID','InvalidParameter')
                # Validate reference encoding before recording a possible external submission.
                image_url(spec)
                remote={'connection':c,'status':'submitting'};record(remote);routes.report(cfg,c,'attempt')
                task_id=submit(cfg,c,spec)
                remote={'connection':c,'taskId':task_id,'status':'submitted'};record(remote);routes.report(cfg,c,'submitted',task_id)
                break
            except (ai.ProviderError,ValueError) as error:
                # Network/5xx failures can have accepted a task even when the reply was lost.
                uncertain=isinstance(error,ai.ProviderError) and (error.code in ['NetworkError','SubmissionUnknown','InvalidResponse'] or (error.status is not None and error.status>=500))
                if uncertain:
                    remote={'connection':c,'status':'submission_unknown'};record(remote)
                    raise ai.ProviderError('视频提交结果未知，请先到平台核对，或填入任务ID继续查询；未切换备用或重复提交','SubmissionUnknown') from None
                record({'connection':c,'status':'rejected'});routes.report(cfg,c,'failed',str(error))
                if index==len(choices)-1 or not routes.retryable(error):raise
                routes.report(cfg,c,'fallback','提交未获接受，切换到 '+choices[index+1]['name'])
    for _ in range(1200):
        if cancel.is_set():raise InterruptedError('本机已暂停查询，云端任务仍可能继续')
        try:status,url=poll(cfg,c,task_id)
        except ai.ProviderError as error:
            if error.code=='RemoteTaskFailed':record({**remote,'status':'failed'})
            raise
        if status!=remote.get('status'):
            remote={**remote,'status':status};record(remote)
        progress(c,status)
        if status=='succeeded':routes.report(cfg,c,'succeeded',task_id);return url,c
        if cancel.wait(3):raise InterruptedError('本机已暂停查询，云端任务仍可能继续')
    raise ai.ProviderError('云端任务仍未完成，可稍后继续查询；不会重复提交','PollTimeout')

def download(url,target,cancel,max_bytes=1024*1024*1024,progress=None):
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:raise ValueError('输出地址必须是HTTPS')
    partial=Path(str(target)+'.part');total=0
    # Media requests never carry the API credential.
    with urllib.request.urlopen(url,timeout=90) as response,partial.open('wb') as f:
        if urllib.parse.urlsplit(response.geturl()).scheme!='https':raise ValueError('视频下载重定向到了非HTTPS地址')
        length=response.headers.get('Content-Length','')
        expected=int(length) if length.isdigit() and int(length)>0 else None
        if expected and expected>max_bytes:raise ValueError('单个输出超过1GB，请在平台下载')
        last=0
        if progress:progress(0,expected)
        while True:
            if cancel.is_set():raise InterruptedError('下载已暂停')
            chunk=response.read(64*1024)
            if not chunk:break
            total+=len(chunk)
            if total>max_bytes:raise ValueError('单个输出超过1GB，请在平台下载')
            f.write(chunk)
            if progress and time.monotonic()-last>=.25:progress(total,expected);last=time.monotonic()
        if expected and total!=expected:raise ValueError('下载文件不完整，请继续原任务重试下载')
        if progress:progress(total,expected)
    if not total:raise ValueError('视频下载为空')
    partial.replace(target)
