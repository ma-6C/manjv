"""Measured task telemetry. Runtime samplers never enter persisted job dictionaries."""
from __future__ import annotations
import copy,math,re,threading,time,uuid
from collections import deque
from pathlib import Path

LOCK=threading.RLock()
SAMPLERS={}
ACTIVE={'running','finalizing'}

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
    return {'format':1,'product':'ManjuStudio','taskId':job['id'],'kind':job['kind'],'status':job['status'],
        'created':job.get('created'),'finished':job.get('finished'),'runSeconds':job.get('runSeconds',0),
        'measurements':rows,'encoding':{k:job.get('encoding',{}).get(k) for k in ('videoEncoder','threadsPerVideo','regroupMode','planVersion','gpuRequested','fallbackCode','fallbackReason','probeProfile')},
        'recovery':recovery(job) if job['status']=='failed' else None,
        'cloudStatus':remote.get('status'),'hasCloudTaskId':bool(remote.get('taskId')),
        'note':'摘要不含接口密钥、授权码、请求正文、原始日志或完整文件路径。'}
