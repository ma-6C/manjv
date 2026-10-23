"""Signed, bounded ZIP64 component import with atomic activation."""
from pathlib import Path,PurePosixPath
import json,zipfile,hashlib,uuid,shutil,threading,copy,os
import licensing
LOCK=threading.RLock();PROGRESS={'status':'idle'}
def safe_path(value):
    if not isinstance(value,str) or '\\' in value or ':' in value:raise ValueError('组件路径无效')
    p=PurePosixPath(value)
    if p.is_absolute() or not p.parts or any(x in ['.','..'] for x in value.split('/')):raise ValueError('组件路径无效')
    return p
def active(home):
    base=Path(home)/'engines';f=base/'active.json'
    if not f.is_file():return {}
    try:
        value=json.loads(f.read_text('utf-8'));folder=base/str(safe_path(value['directory']));meta=json.loads((folder/'engine.json').read_text('utf-8'))
        runtime=folder/str(safe_path(meta['python']));root=folder/str(safe_path(meta['root']))
        if not runtime.is_file() or not root.is_dir():return {}
        return {'id':meta['id'],'root':str(root),'python':str(runtime),'verifiedMode':meta['mode']}
    except (OSError,ValueError,KeyError):return {}
def progress():
    with LOCK:return copy.deepcopy(PROGRESS)
def update(**kwargs):
    with LOCK:PROGRESS.update(kwargs)
def install(archive,home):
    base=(Path(home)/'engines').resolve()
    # Qt contains long upstream resource names; support them without changing OS policy.
    if os.name=='nt' and not str(base).startswith('\\\\?\\'):base=Path('\\\\?\\'+str(base))
    base.mkdir(parents=True,exist_ok=True);stage=base/('_import-'+uuid.uuid4().hex)
    try:
        update(status='verifying',message='校验离线组件签名',percent=0)
        with zipfile.ZipFile(archive) as z:
            entries=z.infolist();names=[i.filename for i in entries]
            if len(entries)>150000 or len(names)!=len(set(names)):raise ValueError('组件文件数异常或存在重名')
            info=z.getinfo('component-signature.json')
            if info.file_size>48*1024*1024:raise ValueError('组件清单过大')
            manifest=licensing.signed_payload(json.loads(z.read(info)))
            if manifest.get('product')!='ManjuStudio' or manifest.get('kind')!='engine' or manifest.get('format')!=1:raise ValueError('不是兼容的 AI 组件')
            files=manifest['files'];total=sum(x['bytes'] for x in files)
            if not files or len(files)>150000 or total>20*1024**3:raise ValueError('组件大小异常')
            expected={str(safe_path(x['path'])):x for x in files}
            if len(expected)!=len(files) or set(names)!=set(expected)|{'component-signature.json'}:raise ValueError('组件文件与签名清单不一致')
            if shutil.disk_usage(base).free<total+512*1024**2:raise ValueError('磁盘空间不足，至少需要 '+str(round(total/1024**3+0.5,1))+' GB')
            stage.mkdir();done=0
            for name,item in expected.items():
                zi=z.getinfo(name)
                if zi.is_dir() or (zi.external_attr>>16)&0o170000==0o120000 or zi.file_size!=item['bytes'] or zi.file_size<0:raise ValueError('组件文件属性无效')
                dest=stage.joinpath(*safe_path(name).parts);dest.parent.mkdir(parents=True,exist_ok=True);h=hashlib.sha256();written=0
                with z.open(zi) as src,dest.open('xb') as out:
                    while chunk:=src.read(1024*1024):
                        written+=len(chunk)
                        if written>item['bytes']:raise ValueError('组件解压大小异常')
                        h.update(chunk);out.write(chunk)
                if written!=item['bytes'] or h.hexdigest()!=item['sha256']:raise ValueError('组件校验失败：'+name)
                done+=written;update(status='installing',message='正在导入离线 AI 引擎',percent=round(done/total*100))
            meta=json.loads((stage/'engine.json').read_text('utf-8'))
            if not (stage/str(safe_path(meta['python']))).is_file() or not (stage/str(safe_path(meta['root']))).is_dir():raise ValueError('组件入口缺失')
            folder='vsr-'+uuid.uuid4().hex[:12];stage.rename(base/folder)
            tmp=base/'active.tmp';tmp.write_text(json.dumps({'directory':folder}),'utf-8');tmp.replace(base/'active.json')
        update(status='completed',message='AI 引擎已就绪',percent=100);return active(home)
    except Exception as e:
        update(status='failed',message=str(e));raise
    finally:
        if stage.is_dir() and stage.resolve().parent==base.resolve() and stage.name.startswith('_import-'):shutil.rmtree(stage)
def start(archive,home,callback):
    with LOCK:
        if PROGRESS['status'] in ['verifying','installing']:raise ValueError('已有组件导入任务')
        update(status='verifying',message='准备导入组件',percent=0)
    def run():
        try:callback(install(archive,home))
        except Exception:pass
    threading.Thread(target=run,daemon=True).start()
