"""Measured task telemetry. Runtime samplers never enter persisted job dictionaries."""
from __future__ import annotations
import copy,math,re,threading,time,uuid
from collections import deque
from pathlib import Path

LOCK=threading.RLock()
SAMPLERS={}
ACTIVE={'running','finalizing'}

def safe_text(value):
    """Keep useful local diagnostics while removing common credential forms."""
    text=str(value)
    text=re.sub(r'(?i)(authorization\s*[:=]\s*)(?:bearer\s+)?[^\s,;]+',r'\1[已隐藏]',text)
    text=re.sub(r'(?i)([?&](?:token|key|api_key|access_token|signature|secret)=)[^&\s]+',r'\1[已隐藏]',text)
    text=re.sub(r'(?i)([\"\x27]?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)[\"\x27]?\s*[:=]\s*)[\"\x27]?[^\s,;\"\x27}]+[\"\x27]?',r'\1[已隐藏]',text)
    return re.sub(r'\bsk-[A-Za-z0-9_-]{12,}', '[已隐藏]', text)

ERROR_LINE=re.compile(r'error|failed|failure|exception|not found|no such|cannot|invalid|denied|out of memory|no space|unable|unsupported|traceback|失败|错误|不足|不存在|找不到|超时',re.I)

def error_excerpt(text,limit=1800):
    lines=list(dict.fromkeys(re.sub(r' @ (?:0x)?[0-9a-fA-F]+(?=\])','',line.strip()) for line in str(text).splitlines() if line.strip()))
    useful=[line for line in lines if ERROR_LINE.search(line) and not line.startswith(('configuration:','libav','libsw','libpost'))]
    return '\n'.join(useful[-6:] or lines[-6:])[:limit]

class ProcessFailure(RuntimeError):
    def __init__(self,tool,exit_code,stderr='',stdout='',timed_out=False):
        self.tool=Path(str(tool)).name
        self.exit_code=exit_code
        self.timed_out=timed_out
        output=str(stderr or stdout)
        if stderr and stdout:output+='\n标准输出：\n'+str(stdout)[-6000:]
        self.details=safe_text(error_excerpt(output,3000)+'\n\n'+output[-12000:])
        reason=error_excerpt(self.details) or '进程未输出错误说明'
        super().__init__(f'{self.tool} '+('执行超时' if timed_out else f'退出码 {exit_code}')+'：'+reason)

class MediaProbeError(ValueError):
    def __init__(self,path,tool,exit_code,details):
        self.details=safe_text(details);self.tool=Path(str(tool)).name;self.exit_code=exit_code
        super().__init__('无法读取视频：'+Path(path).name+'\n'+(error_excerpt(self.details) or '媒体引擎没有返回视频尺寸或时长'))

class OutputValidationError(RuntimeError):
    def __init__(self,message,details='',video='',tool='',exit_code=None):
        self.details=safe_text(details);self.video=video;self.tool=tool;self.exit_code=exit_code
        super().__init__(message+('\n'+error_excerpt(self.details) if self.details.strip() else ''))

def failure(job,error,redact=safe_text,trace=''):
    raw=safe_text(redact(str(error)))
    detail=safe_text(redact(getattr(error,'details',raw)))
    text=(raw+'\n'+detail).lower()
    code,action='TASK_FAILED','根据下方原始报错核对当前步骤；修正后重试未完成部分。'
    rules=[
        ('CUDA_COMPATIBILITY',('no kernel image is available','invalid device function','not compatible with the current pytorch','cuda driver version is insufficient'),'当前显卡与引擎的 PyTorch/CUDA 不兼容。在 AI 去字幕设置中将 STTN 推理设备改为 CPU；使用 GPU 需要匹配显卡型号的运行环境。'),
        ('DISK_SPACE',('no space left','disk full','errno 28','磁盘空间不足','not enough space'),'清理输出磁盘，或在制作设置中更换输出目录，再重试未完成部分。'),
        ('MEMORY',('out of memory','cuda out of memory','cannot allocate memory','显存不足'),'降低并行数或修复批次大小；显存不足时可切换 CPU，再重试当前视频。'),
        ('FILE_MISSING',('no such file','filenotfounderror','系统找不到指定的文件','文件不存在','素材已修改或移动'),'核对下方文件名和路径，恢复缺失文件或重新选择素材。'),
        ('PERMISSION',('permission denied','permissionerror','winerror 5','access is denied'),'检查文件是否被占用，以及输出目录是否可写；关闭占用程序后重试。'),
        ('DEPENDENCY',('modulenotfounderror','no module named','dll load failed','缺少 ffmpeg'),'检查报错中缺失的模块或 DLL，重新配置对应引擎或安装依赖。'),
        ('MEDIA_OUTPUT',('moov atom not found','invalid data found when processing input','error while decoding','sttn stopped before whole video','encoder received no frames'),'输出文件未通过完整性检查。本集未计为完成；先查看下方编码或封装错误，修正后重试当前集。'),
        ('AUTH',('unauthorized','invalid api key','authentication','http error 401','http error 403','鉴权失败','密钥无效'),'到 AI 接口页检查本任务所用连接的密钥、模型权限及余额。'),
        ('FILTER',('no such filter','error initializing filter','error applying option','invalid crop'),'核对本次裁切范围、画幅和滤镜参数，先用短片试处理确认。'),
        ('ENCODER',('no capable devices','unknown encoder','cannot load nvcuda','error while opening encoder','nvenc','amf','qsv'),'检查报错中的编码器和驱动；可关闭 GPU 编码后重试，或重新检测运行环境。'),
        ('PARAMETER',('invalid argument','invalid option','unrecognized option'),'根据原始报错核对所指的输入格式、编码或处理参数，先用短片试处理确认。'),
        ('NETWORK',('timed out','timeout','connection refused','connection reset','urlerror','超时','网络连接'),'检查网络、服务地址和引擎状态；云端任务先核对原任务，再继续查询。'),
    ]
    for key,needles,hint in rules:
        if any(needle in text for needle in needles):code,action=key,hint;break
    if isinstance(error,ProcessFailure) and error.timed_out:
        code,action='PROCESS_TIMEOUT','当前外部程序超过等待上限。核对原始输出和运行环境后重试当前步骤。'
    summary={'CUDA_COMPATIBILITY':'当前显卡与 AI 引擎的 PyTorch/CUDA 不兼容。','DISK_SPACE':'输出磁盘空间不足。','MEMORY':'处理引擎报告内存或显存不足。','FILE_MISSING':'处理所需的文件或目录不存在。',
        'PERMISSION':'处理程序没有文件访问权限。','DEPENDENCY':'引擎缺少模块或运行库。','AUTH':'接口认证未通过。',
        'FILTER':'媒体滤镜未能初始化。','ENCODER':'视频编码器未能正常启动。','PARAMETER':'媒体命令中的参数未被接受。','NETWORK':'连接或服务响应异常。',
        'PROCESS_TIMEOUT':'外部处理程序超过等待上限。','MEDIA_OUTPUT':'生成的视频不完整或无法正常解码。'}.get(code,'当前步骤执行失败，原始报错如下。')
    t=snapshot(job);row=t.get('current') or {}
    stage=job.get('stage')
    if not stage or stage=='任务失败':stage=t.get('phase') or row.get('label') or '未记录失败阶段'
    reason=(error_excerpt(detail) or error_excerpt(raw)) if isinstance(error,ProcessFailure) else error_excerpt(raw)
    if code=='CUDA_COMPATIBILITY':
        reason=next((line.strip() for line in (raw+'\n'+detail).splitlines() if any(marker in line.lower() for marker in rules[0][1])),reason)
    return {'code':code,'stage':stage,'video':getattr(error,'video','') or row.get('name',''),'project':job.get('project',''),
            'summary':summary,'reason':reason,'nextStep':action,'exceptionType':type(error).__name__,
            'tool':getattr(error,'tool',''),'exitCode':getattr(error,'exit_code',None),
            'details':detail,'traceback':safe_text(redact(trace))[-12000:],'time':time.strftime('%Y-%m-%d %H:%M:%S')}

def job_failure(job,redact=safe_text):
    if job.get('status')!='failed':return None
    if job.get('diagnostic'):return job['diagnostic']
    value=failure(job,RuntimeError(job.get('error') or '旧任务没有保存具体报错'),redact=redact)
    finished=job.get('finished')
    value.update(exceptionType='未记录（历史任务）',time=time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(finished)) if isinstance(finished,(int,float)) and finished>0 else '')
    return value

def phase(job,label):
    with LOCK:
        t=job.setdefault('telemetry',{'rows':[]})
        if t.get('phase')!=label:t.update(phase=label,phaseStarted=time.time())
        t['heartbeatAt']=time.time()

def batch(job,key,label,total,done=0):
    with LOCK:
        t=job.setdefault('telemetry',{'rows':[]})
        t['batch']={'key':key,'label':label,'total':max(0,int(total)),'done':max(0,int(done))}

def begin(job,label,name='',total=None,unit='seconds'):
    tid=uuid.uuid4().hex[:12];now=time.time()
    with LOCK:
        t=job.setdefault('telemetry',{'rows':[]})
        t['rows']=[r for r in t['rows'] if r['status'] in ACTIVE][-8:]
        row={'id':tid,'label':label,'name':Path(name).name,'unit':unit,'total':total if total and total>0 else None,
             'completed':0,'percent':None,'status':'running','startedAt':now,'heartbeatAt':now,'progressAt':now,
             'elapsedSeconds':0,'speed':None,'etaSeconds':None}
        t['rows'].append(row);SAMPLERS[tid]={'started':time.monotonic(),'samples':deque(maxlen=30)}
        phase(job,label)
    return tid

def _row(job,tid):return next((r for r in job.get('telemetry',{}).get('rows',[]) if r['id']==tid),None)

def heartbeat(job,tid=None):
    with LOCK:
        now=time.time();t=job.setdefault('telemetry',{'rows':[]});t['heartbeatAt']=now
        row=_row(job,tid)
        if row:
            row['heartbeatAt']=now
            sampler=SAMPLERS.get(tid)
            if sampler:row['elapsedSeconds']=round(time.monotonic()-sampler['started'],1)

def advance(job,tid,completed,total=None):
    if not isinstance(completed,(int,float)) or not math.isfinite(completed) or completed<0:return
    with LOCK:
        row=_row(job,tid)
        if not row or row['status'] not in ACTIVE:return
        heartbeat(job,tid)
        if total and math.isfinite(total) and total>0:row['total']=total
        # A telemetry phase can contain repeated timestamps. Only actual movement updates progressAt.
        value=max(row['completed'],completed)
        if value>row['completed']:row['progressAt']=time.time()
        row['completed']=value
        row['percent']=min(99.9,round(value/row['total']*100,1)) if row['total'] else None
        sampler=SAMPLERS.get(tid)
        if not sampler:return
        now=time.monotonic();samples=sampler['samples']
        if not samples or now-samples[-1][0]>=.4:samples.append((now,value))
        while len(samples)>2 and now-samples[0][0]>12:samples.popleft()
        if len(samples)>=3 and samples[-1][0]-samples[0][0]>=2:
            rate=(samples[-1][1]-samples[0][1])/(samples[-1][0]-samples[0][0])
            row['speed']=round(rate,3) if rate>0 else None
            row['etaSeconds']=round(max(0,row['total']-value)/rate) if row['total'] and rate>0 else None

def restart(job,tid,label):
    """A device retry starts this video's frame count and speed samples again."""
    with LOCK:
        row=_row(job,tid)
        if row:row.update(status='running',label=label,completed=0,percent=0,etaSeconds=None,speed=None,progressAt=time.time())
        sampler=SAMPLERS.get(tid)
        if sampler:sampler['samples'].clear()
        phase(job,label)

def finalizing(job,tid,label='校验输出'):
    with LOCK:
        row=_row(job,tid)
        if row:row.update(status='finalizing',label=label,percent=None,etaSeconds=None,speed=None)
        phase(job,label)

def finish(job,tid):
    with LOCK:
        row=_row(job,tid)
        if row:row.update(status='completed',percent=100,etaSeconds=None,speed=None)
        SAMPLERS.pop(tid,None)

def settle(job,status):
    with LOCK:
        for row in job.get('telemetry',{}).get('rows',[]):
            if row['status'] in ACTIVE:
                heartbeat(job,row['id']);row.update(status=status,speed=None,etaSeconds=None)
            SAMPLERS.pop(row['id'],None)

def snapshot(job):
    with LOCK:
        value=copy.deepcopy(job.get('telemetry',{'rows':[]}))
    rows=value.get('rows',[])
    value['current']=next((r for r in rows if r['status'] in ACTIVE),rows[-1] if rows and job.get('status')!='running' else None)
    value['activeCount']=sum(r['status'] in ACTIVE for r in rows)
    return value

def ffmpeg_event(job,tid,line):
    key,_,value=line.strip().partition('=')
    if key in ['out_time_us','out_time_ms']:
        try:advance(job,tid,int(value)/1_000_000)
        except ValueError:pass
    elif key=='progress':heartbeat(job,tid)

def vsr_event(job,tid,line):
    # The signed v1 engine writes tqdm frame counts to stdout, separated by carriage returns.
    if 'Subtitle Removing' not in line:return
    found=re.search(r'\|\s*(\d+)\s*/\s*(\d+)',line)
    if found:
        n,total=map(int,found.groups())
        if not total:return
        with LOCK:
            row=_row(job,tid)
            if row:row.update(label='AI 修复字幕区域',unit='frames')
        advance(job,tid,n,total)
        if n>=total:finalizing(job,tid,'修复帧已完成，正在合成音轨／收尾')

def recovery(job):
    if job.get('diagnostic'):
        d=job['diagnostic'];return {'code':d['code'],'message':d['reason'],'action':d['nextStep']}
    error=str(job.get('error','')).lower()
    if any(x in error for x in ['space','磁盘','no space','errno 28']):return {'code':'DISK_SPACE','message':'输出磁盘空间不足或无法写入，请检查空间和权限后重试。','action':'重试未完成部分'}
    if any(x in error for x in ['401','403','鉴权','密钥','unauthorized']):return {'code':'AUTH','message':'接口认证或权限未通过，请检查对应连接的密钥、模型和权限。','action':'检查接口设置'}
    if any(x in error for x in ['网络','network','超时','timeout','连接失败']):return {'code':'NETWORK','message':'网络或服务响应异常。云端任务如已提交，请先核对原任务再继续查询。','action':'查看任务与日志'}
    return {'code':'TASK_FAILED','message':'任务未完成，请查看详细错误；已完成的检查点保留。','action':'查看任务与日志'}

def report(job):
    t=snapshot(job)
    # Allowlist only: no raw config, request bodies, full filesystem paths or unfiltered errors/logs.
    rows=[{k:r.get(k) for k in ['label','unit','completed','total','percent','status','elapsedSeconds','progressAt']} for r in t.get('rows',[])]
    remote=job.get('remoteVideo',{})
    diagnostic=job.get('diagnostic')
    def exported(value):
        text=safe_text(value)
        for secret in job.get('config',{}).values():
            if isinstance(secret,str) and len(secret)>8 and secret in text:text=text.replace(secret,'[已隐藏]')
        return re.sub(r'[A-Za-z]:[\\/][^\r\n\"<>]*|/(?:Users|home|tmp|mnt)/[^\r\n\"<>]*','[本地路径]',text)
    failed={k:diagnostic.get(k) for k in ('code','stage','video','summary','reason','nextStep','exceptionType','tool','exitCode','time')} if diagnostic else None
    if failed:failed={k:exported(v) if isinstance(v,str) else v for k,v in failed.items()}
    recover=recovery(job) if job['status']=='failed' else None
    if recover:recover={k:exported(v) for k,v in recover.items()}
    return {'format':2,'product':'ManjuStudio','taskId':job['id'],'kind':job['kind'],'status':job['status'],
        'created':job.get('created'),'finished':job.get('finished'),'runSeconds':job.get('runSeconds',0),
        'measurements':rows,'encoding':{k:job.get('encoding',{}).get(k) for k in ('videoEncoder','threadsPerVideo','regroupMode','planVersion','gpuRequested','fallbackCode','fallbackReason','probeProfile')},
        'recovery':recover,
        'failure':failed,
        'cloudStatus':remote.get('status'),'hasCloudTaskId':bool(remote.get('taskId')),
        'note':'摘要不含接口密钥、授权码、请求正文、原始日志或完整文件路径。'}
