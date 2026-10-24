"""Named API connections, independent credentials and explicit routing policy."""
from __future__ import annotations
import copy,re,time
import ai_providers as ai

CHANNELS={'text':'文字','image':'封面生图','subtitle':'云端字幕'}
PROTOCOLS={'text':ai.TEXT_PROTOCOLS,'image':ai.IMAGE_PROTOCOLS,
           'subtitle':{'subtitle_json'}}
FIELDS={'id','name','channel','provider','protocol','base','model','enabled','tier','thinking','size','submitPath','pollPath'}
TRACE_CALLBACKS={}

def retire_video_config(cfg):
    """Migrate saved configuration only; new video connections remain invalid."""
    entries=cfg.get('aiConnections')
    if isinstance(entries,list):cfg['aiConnections']=[c for c in entries if not isinstance(c,dict) or c.get('channel')!='video']
    for field in ('aiRouting','aiSelection'):
        if isinstance(cfg.get(field),dict):cfg[field].pop('video',None)
    return cfg

def validate(cfg):
    entries=cfg.get('aiConnections',[])
    if not isinstance(entries,list) or len(entries)>100:raise ValueError('接口列表最多100条连接')
    seen=set();clean=[]
    for raw in entries:
        if not isinstance(raw,dict) or set(raw)-FIELDS:raise ValueError('接口记录含未知字段；密钥须通过独立入口设置，不能保存到配置')
        c=copy.deepcopy(raw)
        for key in ['id','name','channel','provider','protocol','base','model']:
            if not isinstance(c.get(key,''),str):raise ValueError('接口字段必须为文本')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',c.get('id','')) or c['id'] in seen:raise ValueError('接口ID无效或重复')
        seen.add(c['id']);c['name']=c.get('name','').strip()
        if not c['name'] or len(c['name'])>80:raise ValueError('连接名称须为1至80字')
        if c['channel'] not in CHANNELS or c['protocol'] not in PROTOCOLS[c['channel']]:raise ValueError('接口用途与协议不匹配')
        if c['provider'] not in {p['id'] for p in ai.PRESETS}:raise ValueError('平台无效')
        c['base']=ai.normalize_url(c['base']);c.setdefault('model','')
        if len(c['model'])>200:raise ValueError('模型ID过长')
        c.setdefault('enabled',True)
        if not isinstance(c['enabled'],bool):raise ValueError('启用状态无效')
        c.setdefault('tier','default');c.setdefault('thinking','default');c.setdefault('size','1024x1536')
        if c['tier'] not in ['default','auto','fast','flex'] or c['thinking'] not in ['default','disabled','enabled']:raise ValueError('推理参数无效')
        if not isinstance(c['size'],str) or len(c['size'])>40:raise ValueError('图片尺寸参数无效')
        for key,default in [('submitPath','/video/clear'),('pollPath','/video/status')]:
            path=c.setdefault(key,default)
            if not isinstance(path,str) or not re.fullmatch(r'/[A-Za-z0-9_./{}-]{0,180}',path) or path.startswith('//') or '..' in path:raise ValueError('提交/查询路径须为同一接口下的相对路径')
        clean.append(c)
    cfg['aiConnections']=clean
    routing=cfg.get('aiRouting',{});selection=cfg.get('aiSelection',{})
    if not isinstance(routing,dict) or set(routing)-set(CHANNELS) or not isinstance(selection,dict) or set(selection)-set(CHANNELS):raise ValueError('接口路由配置无效')
    for channel in CHANNELS:
        ids={c['id'] for c in clean if c['channel']==channel}
        rule=routing.setdefault(channel,{'primary':'','backups':[],'autoFallback':False})
        if not isinstance(rule,dict) or set(rule)-{'primary','backups','autoFallback'}:raise ValueError('主备规则无效')
        rule.setdefault('primary','');rule.setdefault('backups',[]);rule.setdefault('autoFallback',False)
        if not isinstance(rule['backups'],list) or any(not isinstance(x,str) or x not in ids for x in rule['backups']):raise ValueError('备用连接不属于该用途')
        if rule['primary'] and rule['primary'] not in ids:raise ValueError('主用连接不属于该用途')
        if len(rule['backups'])!=len(set(rule['backups'])) or rule['primary'] in rule['backups']:raise ValueError('主备连接不能重复')
        if not isinstance(rule['autoFallback'],bool):raise ValueError('自动切换设置无效')
        chosen=selection.setdefault(channel,'auto')
        if chosen not in ['auto','legacy'] and chosen not in ids:raise ValueError('任务选择的接口不存在或用途不匹配')
    cfg['aiRouting']=routing;cfg['aiSelection']=selection
    return cfg

def bound(cfg,c):
    options=copy.deepcopy(cfg);options.update(_aiDirect=True,_aiConnection=copy.deepcopy(c))
    return options

def candidates(cfg,channel):
    if channel not in CHANNELS:raise ValueError('接口用途无效或已移除')
    chosen=cfg.get('aiSelection',{}).get(channel,'auto')
    entries=[c for c in cfg.get('aiConnections',[]) if c['channel']==channel]
    if chosen=='legacy' or (chosen=='auto' and not entries):return []
    rule=cfg.get('aiRouting',{}).get(channel,{})
    ids=[chosen] if chosen!='auto' else [rule.get('primary','')]+(rule.get('backups',[]) if rule.get('autoFallback') else [])
    result=[next((c for c in entries if c['id']==cid),None) for cid in ids if cid]
    result=[c for c in result if c and c.get('enabled',True)]
    if not result:raise ai.ProviderError(f'请为{CHANNELS[channel]}选择已启用的连接，或设置默认主用连接','NoConnection')
    return result

def report(cfg,c,event,detail=''):
    callback=cfg.get('_aiTrace') or TRACE_CALLBACKS.get(cfg.get('_aiTraceId'))
    if callback:callback({'channel':c['channel'],'connectionId':c['id'],'name':c['name'],'provider':c['provider'],'model':c['model'],
                          'event':event,'detail':ai.redact(detail),'time':time.time()})

def retryable(error):
    if not isinstance(error,ai.ProviderError):return False
    if error.code in ['ContentFilter','ContentPolicyViolation','DataInspectionFailed','InvalidParameter','InvalidResponse','EmptyOutput','NoImage','SubmissionUnknown']:return False
    return error.code in ['MissingKey','NetworkError','InvalidApiKey','AuthenticationError','ModelNotOpen'] or error.status in [401,403,404,408,429] or (error.status is not None and error.status>=500)

def require_key(cfg,c):
    key=ai.get_key(bound(cfg,c),c['channel'])
    if not key:raise ai.ProviderError(f'连接「{c["name"]}」尚未设置本次会话密钥','MissingKey')
    return key

def routed(cfg,channel,action):
    choices=candidates(cfg,channel)
    if not choices:return action(cfg|{'_aiDirect':True})
    for index,c in enumerate(choices):
        report(cfg,c,'attempt')
        try:
            require_key(cfg,c)
            result=action(bound(cfg,c));report(cfg,c,'succeeded');return result
        except (ai.ProviderError,ValueError) as error:
            report(cfg,c,'failed',str(error))
            if index==len(choices)-1 or not retryable(error):raise
            report(cfg,c,'fallback',f'切换到 {choices[index+1]["name"]}')

def key_status(cfg):
    return {c['id']:bool(ai.get_key(bound(cfg,c),c['channel'])) for c in cfg.get('aiConnections',[])}
