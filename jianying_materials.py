"""Discover Jianying's downloaded audio and classify actual media duration.

The reference's recovered material constants use BGM >=100s and SFX 1.5-15s.
Only existing local media are read. Downloading audio is left to Jianying.
"""
from pathlib import Path
import hashlib
import math
import os
import threading

BGM_MIN_SECONDS=100.
SFX_MIN_SECONDS=1.5
SFX_MAX_SECONDS=15.
MAX_BYTES=128*1024**2
MAX_FILES=3000
EXTENSIONS={'.mp3','.wav','.m4a','.aac','.flac','.ogg','.opus','.wma'}
_CACHE={}
_LOCK=threading.Lock()


def resolve_material_dir(configured='',extra_roots=()):
    candidates=[]
    if configured:
        base=Path(configured).expanduser()
        for root in (base,base/'JianyingPro'):
            candidates.extend(root/part for part in ('User Data/Cache/music','User Data/Cloud files','Cache/music'))
        installed=any((root/'JianyingPro.exe').is_file() for root in (base,base/'JianyingPro'))
        if not installed:candidates.append(base)
    candidates.extend(Path(root) for root in extra_roots if root)
    local=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'JianyingPro'/'User Data'
    candidates.extend((local/'Cache/music',local/'Cloud files'))
    for candidate in candidates:
        if candidate.is_dir():return str(candidate.resolve())
    return ''


def _files(folder):
    root=Path(folder).resolve();files=[]
    def ordinary(path):
        stat=path.lstat()
        return not path.is_symlink() and not getattr(stat,'st_file_attributes',0)&0x400
    for directory,dirs,names in os.walk(root,followlinks=False):
        parent=Path(directory)
        dirs[:]=sorted(name for name in dirs if ordinary(parent/name))
        if len(parent.relative_to(root).parts)>=3:dirs.clear()
        for name in names:
            path=parent/name
            try:
                if path.suffix.lower() not in EXTENSIONS or not ordinary(path):continue
                stat=path.stat()
                if 0<stat.st_size<=MAX_BYTES:files.append((path,stat.st_size,stat.st_mtime_ns))
            except OSError:continue
        # Bound directory traversal as well as duration probing. Prefer newer
        # files among the candidates encountered; never traverse reparse dirs.
        if len(files)>=MAX_FILES:break
    return sorted(files,key=lambda row:(-row[2],str(row[0])))[:MAX_FILES]


def scan_materials(folder,event,notify=lambda *args:None):
    result={'directory':folder,'bgm':[],'sfx':[],'unreadable':0,'scanned':0}
    if not folder:return result
    files=_files(folder)
    if not files:return result
    from pyJianYingDraft import AudioMaterial
    for index,(path,size,modified) in enumerate(files):
        if event.is_set():raise InterruptedError('声音素材识别已暂停')
        key=(str(path),size,modified)
        with _LOCK:known=key in _CACHE;duration=_CACHE.get(key)
        if not known:
            try:duration=AudioMaterial(str(path)).duration/1e6
            except (ValueError,OSError,RuntimeError):duration=0.
            if not isinstance(duration,(float,int)) or not math.isfinite(duration) or duration<0:duration=0.
            with _LOCK:
                if len(_CACHE)>MAX_FILES*2:_CACHE.clear()
                _CACHE[key]=duration
        if duration>=BGM_MIN_SECONDS:result['bgm'].append(path)
        elif SFX_MIN_SECONDS<=duration<=SFX_MAX_SECONDS:result['sfx'].append(path)
        elif duration<=0:result['unreadable']+=1
        result['scanned']+=1;notify('materials',index+1,len(files))
    return result


def _choose(files,count,uses,seed):
    def rank(path):
        return (uses.get(str(path),0),-path.stat().st_mtime_ns,hashlib.sha256((seed+str(path)).encode()).hexdigest())
    chosen=sorted(files,key=rank)[:count]
    for path in chosen:uses[str(path)]=uses.get(str(path),0)+1
    return chosen


def prepare(video,opts,job,event,notify=lambda *args:None):
    """Freeze automatic picks before copying them into this episode's draft."""
    if not opts['materialLibrary']:
        video['jianyingLibraryFiles']={'bgm':[],'sfx':[]}
        video['jianyingMaterialReport']={'directory':'','scanned':0,'bgm':0,'sfx':0,'unreadable':0}
        return
    previous=video.get('jianyingLibraryFiles')
    if previous is not None:
        expected=video.get('jianyingAssets',{})
        for values in previous.values():
            for name in values:
                path=Path(name)
                if not path.is_file():raise ValueError('已选择的剪映声音素材被移走，请恢复后重试：'+path.name)
                stat=path.stat()
                if expected.get(str(path.resolve()))!={'bytes':stat.st_size,'mtime':stat.st_mtime_ns}:
                    raise ValueError('已选择的剪映声音素材已变化，请重新建立任务：'+path.name)
        return
    root=Path(opts['materialLibrary']);name=video.get('projectName','')+' '+video['name']
    uses=job.setdefault('jianyingMaterialUses',{})
    if (root/'bgm').is_dir() or (root/'sfx').is_dir():
        # Preserve explicitly organised libraries from earlier versions.
        from jianying_editing import library_files,select_materials
        pools={key:library_files(root/key) if (root/key).is_dir() else [] for key in ('bgm','sfx')}
        picked={key:select_materials(pools[key],name,opts['mood'],1 if key=='bgm' else 3) for key in pools}
        report={'directory':str(root),'scanned':sum(map(len,pools.values())),'bgm':len(pools['bgm']),'sfx':len(pools['sfx']),'unreadable':0}
    else:
        catalog=scan_materials(str(root),event,notify)
        picked={key:_choose(catalog[key],1 if key=='bgm' else 3,uses,name) if key!='bgm' or opts['addBgm'] else [] for key in ('bgm','sfx')}
        report={**catalog,'bgm':len(catalog['bgm']),'sfx':len(catalog['sfx'])}
    if not opts['addBgm'] or opts['musicPath']:picked['bgm']=[]
    if opts['soundEffectPath']:picked['sfx']=[]
    snapshots=video.setdefault('jianyingAssets',{})
    for files in picked.values():
        for path in files:
            stat=path.stat();snapshots[str(path.resolve())]={'bytes':stat.st_size,'mtime':stat.st_mtime_ns}
    video['jianyingLibraryFiles']={key:[str(p.resolve()) for p in files] for key,files in picked.items()}
    video['jianyingMaterialReport']=report
