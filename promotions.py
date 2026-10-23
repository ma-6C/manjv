"""Local promotion preparation and explicitly human-confirmed platform receipts."""
from pathlib import Path
from decimal import Decimal,InvalidOperation
from urllib.parse import urlsplit
import json,copy,uuid,time,hashlib,re,io,csv
TYPES={'native':'视频号原生剧集','mini_program':'短剧小程序','third_party':'第三方推广平台'}
OFFICIAL='https://channels.weixin.qq.com/platform'
def text(value,name,limit=300,required=False):
    if not isinstance(value,str) or len(value)>limit or any(ord(c)<32 and c not in '\n\t' for c in value):raise ValueError(name+'格式无效')
    value=value.strip()
    if required and not value:raise ValueError('请填写'+name)
    return value
def url(value,name,required=False):
    value=text(value,name,2000,required)
    if not value:return ''
    u=urlsplit(value)
    if u.scheme!='https' or not u.hostname or u.username or u.password or any(c.isspace() for c in value):raise ValueError(name+'必须为有效的 HTTPS 地址')
    return value
def entry(value):
    if not isinstance(value,dict):raise ValueError('推广入口格式无效')
    kind=value.get('type','native')
    if kind not in TYPES:raise ValueError('推广入口类型无效')
    result={'type':kind,'dramaTitle':text(value.get('dramaTitle',''),'平台剧名',100,True),
            'dramaId':text(value.get('dramaId',''),'平台剧集 ID',200,kind!='mini_program'),
            'entryUrl':url(value.get('entryUrl',''),'全集入口链接'),
            'appId':text(value.get('appId',''),'小程序 AppID',100,kind=='mini_program'),
            'pagePath':text(value.get('pagePath',''),'小程序页面路径',1000,kind=='mini_program'),
            'provider':text(value.get('provider',''),'推广平台名称',100,kind=='third_party'),
            'backendUrl':url(value.get('backendUrl','') or (OFFICIAL if kind!='third_party' else ''),'发布后台地址',True),
            'notes':text(value.get('notes',''),'入口备注',2000)}
    if kind=='mini_program':
        if not re.fullmatch(r'wx[a-zA-Z0-9]{16}',result['appId']):raise ValueError('小程序 AppID 应为 wx 开头的18位标识')
        if result['pagePath'].startswith(('/','\\')) or '://' in result['pagePath'] or '..' in result['pagePath'].split('/'):raise ValueError('请填写小程序内的页面路径，例如 pages/play/index?drama_id=...')
    return result
def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def task(state,tid):
    row=next((x for x in state['promotionTasks'] if x['id']==tid),None)
    if row is None:raise ValueError('推广任务不存在')
    return row
def make_task(state,project,body):
    if not project.get('rights'):raise ValueError('请先确认素材制作与发布授权')
    profile=entry(body.get('entry') or project.get('promotionEntry',{}))
    clip=next((c for c in project.get('promotionClips',[]) if c['id']==body.get('clipId')),None)
    if not clip:raise ValueError('请选择该剧已生成的钩子素材')
    path=Path(clip['path'])
    if not path.is_file() or path.stat().st_size!=clip['bytes'] or path.stat().st_mtime_ns!=clip['mtimeNs']:raise ValueError('钩子素材已修改或移动，请重新制作')
    account=next((a for a in state['accounts'] if a['id']==body.get('accountId')),None)
    if not account:raise ValueError('请选择推广账号备注')
    # Repeated clicks reuse an unsubmitted identical task, avoiding accidental duplication.
    fp=fingerprint(profile)
    previous=next((x for x in state['promotionTasks'] if x['projectId']==project['id'] and x['clipId']==clip['id'] and x['accountId']==account['id'] and x['entryFingerprint']==fp and x['status']=='prepared'),None)
    if previous:return copy.deepcopy(previous)
    if len(state['promotionTasks'])>=10000:raise ValueError('推广任务记录已达上限，请先备份整理')
    row={'id':uuid.uuid4().hex[:16],'projectId':project['id'],'projectName':project['name'],'clipId':clip['id'],
         'clip':copy.deepcopy(clip),'accountId':account['id'],'accountName':account['name'],'entry':profile,'entryFingerprint':fp,
         'status':'prepared','mountStatus':'pending','createdAt':time.time(),'updatedAt':time.time(),'receipts':[]}
    state['promotionTasks'].append(row);return copy.deepcopy(row)
def record(state,body):
    row=task(state,body.get('taskId'));status=body.get('status')
    if status not in ['mounted','failed']:raise ValueError('请选择人工核对结果')
    if body.get('checked') is not True:raise ValueError('请先在平台实际核对发布和挂载结果')
    if row['status']=='cancelled':raise ValueError('已取消的任务不能确认挂载')
    ref=text(body.get('postId',''),'平台作品 ID',200);link=url(body.get('postUrl',''),'作品链接')
    note=text(body.get('note',''),'核对说明',2000,True)
    if status=='mounted' and not(ref or link):raise ValueError('请提供作品 ID 或作品链接作为核对依据')
    receipt={'id':uuid.uuid4().hex[:12],'source':'manual','status':status,'postId':ref,'postUrl':link,'note':note,'at':time.time()}
    row['receipts'].append(receipt);row.update(status='submitted' if status=='mounted' else 'failed',mountStatus='user_confirmed' if status=='mounted' else 'failed',updatedAt=time.time())
    return copy.deepcopy(row)
def date(value):
    from datetime import date as dt
    value=text(value,'统计日期',10,True)
    try:dt.fromisoformat(value)
    except ValueError:raise ValueError('日期请使用 YYYY-MM-DD') from None
    return value
def integer(value,name):
    if isinstance(value,bool) or not str(value).isdigit() or int(value)>10**12:raise ValueError(name+'须为非负整数')
    return int(value)
def cents(value):
    try:
        amount=Decimal(str(value))
        if not amount.is_finite() or amount<0 or amount>Decimal('100000000') or amount!=amount.quantize(Decimal('.01')):raise InvalidOperation
        return int(amount*100)
    except (InvalidOperation,ValueError):raise ValueError('广告分成金额须为最多两位小数的非负数') from None
def revenue_row(state,value):
    row=task(state,value.get('taskId'))
    if row['mountStatus']!='user_confirmed':raise ValueError('请先完成人工挂载核对，再录入收益')
    return {'taskId':row['id'],'date':date(value.get('date','')),'views':integer(value.get('views',0),'播放量'),
            'clicks':integer(value.get('clicks',0),'入口点击量'),'unlocks':integer(value.get('unlocks',0),'广告解锁量'),
            'revenueCents':cents(value.get('revenue',0)),'note':text(value.get('note',''),'数据备注',1000)}
def save_revenues(state,values,source='manual'):
    if not isinstance(values,list) or not values or len(values)>1000:raise ValueError('一次请录入1至1000行数据')
    rows=[revenue_row(state,x) for x in values];keys=[(x['taskId'],x['date']) for x in rows]
    if len(keys)!=len(set(keys)):raise ValueError('同一批数据存在重复的任务与日期')
    if len(state['promotionRevenue'])+len(rows)>100000:raise ValueError('收益记录已达上限')
    for row in rows:
        previous=next((x for x in state['promotionRevenue'] if x['taskId']==row['taskId'] and x['date']==row['date']),None)
        value={**row,'source':source,'updatedAt':time.time()}
        if previous:previous.update(value)
        else:state['promotionRevenue'].append(value)
    return {'saved':len(rows),'summary':summary(state)}
def import_csv(state,content):
    if not isinstance(content,str) or len(content)>600000:raise ValueError('CSV 内容过大')
    reader=csv.DictReader(io.StringIO(content.lstrip('\ufeff')))
    required={'taskId','date','revenue'}
    if not required.issubset(reader.fieldnames or []):raise ValueError('CSV 至少需要 taskId,date,revenue 三列，请使用下载的模板')
    return save_revenues(state,list(reader),'csv')
def summary(state):
    rows=state['promotionRevenue']
    return {'revenueCents':sum(r['revenueCents'] for r in rows),'views':sum(r['views'] for r in rows),
            'clicks':sum(r['clicks'] for r in rows),'unlocks':sum(r['unlocks'] for r in rows),'rows':len(rows),'source':'manual_or_csv'}
def csv_export(state,template=False):
    out=io.StringIO(newline='');fields=['taskId','date','views','clicks','unlocks','revenue','note'];writer=csv.DictWriter(out,fieldnames=fields);writer.writeheader()
    if not template:
        for row in state['promotionRevenue']:
            value={k:row[k] for k in fields if k not in ['revenue','note']};value['revenue']=str(Decimal(row['revenueCents'])/100)
            # Prevent spreadsheet formulas from user-controlled free text.
            note=row['note'];value['note']="'"+note if note.startswith(('=','+','-','@','\t','\r')) else note;writer.writerow(value)
    return out.getvalue().encode('utf-8-sig')
