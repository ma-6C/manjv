"""Editable Jianying projects from real media and measured scene intervals."""
from pathlib import Path
import hashlib,json,os,re,shutil,time,uuid,importlib.metadata
import ctypes,subprocess,threading
import jianying_timeline

_IMPORT_LOCK=threading.Lock()
_VERSION_CACHE={}
_SIGNATURE_CACHE={}
_EDITOR_DIAGNOSTICS={}

def options(value=None):
    value=value or {}
    if not isinstance(value,dict) or set(value)-({'output','splitScenes','executable','draftRoot'}|set(jianying_timeline.DEFAULTS)):raise ValueError('剪映工程设置无效')
    out={'output':'','splitScenes':True,'executable':'','draftRoot':''}|value
    if type(out['splitScenes']) is not bool:raise ValueError('镜头分段设置无效')
    for name in ('output','executable','draftRoot'):
        if not isinstance(out[name],str) or len(out[name])>2000 or any(ord(c)<32 for c in out[name]):raise ValueError('工程路径无效')
        if out[name] and not Path(out[name]).is_absolute():raise ValueError('请选择绝对路径')
    return jianying_timeline.options(out)

def _file_version(path):
    """Read Windows PE metadata without running the selected executable."""
    path=Path(path)
    if os.name!='nt' or not path.is_file():return {}
    stat=path.stat();key=(str(path).casefold(),stat.st_size,stat.st_mtime_ns)
    if key in _VERSION_CACHE:return dict(_VERSION_CACHE[key])
    try:
        from ctypes import wintypes
        dll=ctypes.WinDLL('version',use_last_error=True)
        dll.GetFileVersionInfoSizeW.argtypes=[wintypes.LPCWSTR,ctypes.POINTER(wintypes.DWORD)]
        dll.GetFileVersionInfoSizeW.restype=wintypes.DWORD
        dll.GetFileVersionInfoW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID]
        dll.GetFileVersionInfoW.restype=wintypes.BOOL
        dll.VerQueryValueW.argtypes=[wintypes.LPCVOID,wintypes.LPCWSTR,ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(wintypes.UINT)]
        dll.VerQueryValueW.restype=wintypes.BOOL
        ignored=wintypes.DWORD();length=dll.GetFileVersionInfoSizeW(str(path),ctypes.byref(ignored))
        if not length or length>8*1024*1024:return {}
        data=ctypes.create_string_buffer(length)
        if not dll.GetFileVersionInfoW(str(path),0,length,data):return {}
        pointer=ctypes.c_void_p();size=wintypes.UINT()
        if not dll.VerQueryValueW(data,'\\',ctypes.byref(pointer),ctypes.byref(size)) or size.value<52:return {}
        fixed=ctypes.cast(pointer,ctypes.POINTER(ctypes.c_uint32*13)).contents
        if fixed[0]!=0xFEEF04BD:return {}
        version='.'.join(str(v) for n in fixed[2:4] for v in (n>>16,n&65535))
        translations=[]
        if dll.VerQueryValueW(data,'\\VarFileInfo\\Translation',ctypes.byref(pointer),ctypes.byref(size)):
            words=ctypes.cast(pointer,ctypes.POINTER(ctypes.c_ushort))
            translations=[(words[i],words[i+1]) for i in range(0,min(size.value//2,32)-1,2)]
        translations+= [(0x409,0x4B0),(0x804,0x4B0)]
        result={'version':version}
        for field in ('ProductName','OriginalFilename','CompanyName','FileDescription'):
            for language,codepage in translations:
                query='\\StringFileInfo\\%04x%04x\\%s'%(language,codepage,field)
                if dll.VerQueryValueW(data,query,ctypes.byref(pointer),ctypes.byref(size)) and size.value:
                    result[field]=ctypes.wstring_at(pointer,size.value).rstrip('\0');break
        _VERSION_CACHE.clear() if len(_VERSION_CACHE)>50 else None
        _VERSION_CACHE[key]=result
        return dict(result)
    except (OSError,ValueError,AttributeError):return {}

def _signature(path):
    """Check the executable signature, without interpolating paths into code."""
    path=Path(path)
    if os.name!='nt' or not path.is_file():return {'valid':False,'status':'unavailable','publisher':''}
    stat=path.stat();key=(str(path).casefold(),stat.st_size,stat.st_mtime_ns)
    if key in _SIGNATURE_CACHE:return dict(_SIGNATURE_CACHE[key])
    script="$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[System.Text.Encoding]::UTF8; $s=Get-AuthenticodeSignature -LiteralPath $env:MANJU_JY_SIGNATURE_FILE; [pscustomobject]@{status=[string]$s.Status;publisher=[string]$s.SignerCertificate.Subject} | ConvertTo-Json -Compress"
    env=os.environ.copy();env['MANJU_JY_SIGNATURE_FILE']=str(path)
    # Prefer an installed PowerShell Core when the host uses it. Inheriting its
    # module path into Windows PowerShell 5 can prevent Security from loading.
    shell=shutil.which('pwsh') or str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe')
    env.pop('PSModulePath',None)
    try:
        result=subprocess.run([shell,'-NoProfile','-NonInteractive','-Command',script],env=env,
            capture_output=True,timeout=10,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        value=json.loads(result.stdout.decode('utf-8-sig')) if not result.returncode else {}
        publisher=str(value.get('publisher',''))
        publisher_names=[part.strip().strip('"') for part in re.findall(r'(?:^|,\s*)(?:CN|O)=([^,]+)',publisher)]
        official='深圳市脸萌科技有限公司' in publisher_names
        checked={'valid':value.get('status')=='Valid' and official,'status':str(value.get('status','unavailable')),
                 'publisher':publisher,'officialPublisher':official}
    except subprocess.TimeoutExpired:
        return {'valid':False,'status':'timeout','publisher':'','note':'剪映数字签名检查超时，请稍后重新检测或检查Windows证书验证环境。'}
    except (OSError,ValueError):
        return {'valid':False,'status':'unavailable','publisher':'','note':'无法验证剪映数字签名，请先检查官方安装文件。'}
    _SIGNATURE_CACHE.clear() if len(_SIGNATURE_CACHE)>50 else None
    _SIGNATURE_CACHE[key]=checked
    return dict(checked)

def _verified_editor(path):
    if not path:return None
    path=Path(path).expanduser().resolve()
    if path.name.casefold()!='jianyingpro.exe' or not path.is_file():return None
    info=_file_version(path)
    product=' '.join(str(info.get(k,'')) for k in ('ProductName','FileDescription','OriginalFilename')).casefold()
    if not info.get('version') or info['version']=='0.0.0.0' or not re.fullmatch(r'\d+\.\d+\.\d+\.\d+',info['version']) or not any(x in product for x in ('jianying','剪映')):return None
    signed=_signature(path)
    if not signed.get('valid'):
        _EDITOR_DIAGNOSTICS[str(path)]=signed.get('note') or ('主程序数字签名不是有效的剪映官方发行者，已阻止启动。发行者：'+signed.get('publisher','未提供'))
        return None
    _EDITOR_DIAGNOSTICS.pop(str(path),None)
    return {'path':str(path),'version':info['version'],'product':info.get('ProductName',''),
            'company':info.get('CompanyName',''),'metadataVerified':True,'signatureVerified':True,
            'signaturePublisher':signed.get('publisher',''),'signatureStatus':signed.get('status','')}

def _editor_candidates():
    roots=[Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'JianyingPro',
           Path(os.environ.get('PROGRAMFILES','C:/Program Files'))/'JianyingPro',
           Path(os.environ.get('PROGRAMFILES(X86)','C:/Program Files (x86)'))/'JianyingPro']
    if os.name=='nt':
        # Probe a few known install folder names on fixed disks, never a full
        # drive traversal. Covers explicitly user-selected custom installs.
        bits=ctypes.windll.kernel32.GetLogicalDrives()
        for offset in range(26):
            if bits & (1<<offset):
                drive=chr(65+offset)+':/'
                if ctypes.windll.kernel32.GetDriveTypeW(drive)==3:
                    roots.extend(Path(drive)/p for p in ('剪映/JianyingPro','剪映','JianyingPro','Program Files/JianyingPro'))
    registry=[]
    if os.name=='nt':
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
            for view in (0,winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive,r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\JianyingPro.exe',0,winreg.KEY_READ|view) as key:
                        registry.append(Path(winreg.QueryValue(key,None).strip('"')))
                except OSError:pass
            for subkey in (r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'):
                try:
                    with winreg.OpenKey(hive,subkey) as base:
                        for index in range(min(winreg.QueryInfoKey(base)[0],2000)):
                            try:
                                with winreg.OpenKey(base,winreg.EnumKey(base,index)) as key:
                                    name=winreg.QueryValueEx(key,'DisplayName')[0]
                                    if not any(t in str(name).casefold() for t in ('jianying','剪映')):continue
                                    try:roots.append(Path(winreg.QueryValueEx(key,'InstallLocation')[0]))
                                    except OSError:pass
                                    try:
                                        icon=str(winreg.QueryValueEx(key,'DisplayIcon')[0])
                                        registry.append(Path(icon.split('"')[1] if icon.startswith('"') else icon.rsplit(',',1)[0]))
                                    except OSError:pass
                            except OSError:pass
                except OSError:pass
    candidates=list(registry)
    for root in dict.fromkeys(roots):
        if not str(root).strip() or not root.is_absolute():continue
        for directory in (root,root/'App',root/'Apps'):
            candidates.append(directory/'JianyingPro.exe')
            if directory.is_dir():
                children=sorted((p for p in directory.iterdir() if p.is_dir() and re.match(r'^\d',p.name)),key=lambda p:[int(n) for n in re.findall(r'\d+',p.name)],reverse=True)
                candidates.extend(child/'JianyingPro.exe' for child in children[:30])
    return list(dict.fromkeys(str(p) for p in candidates))

def _draft_roots(opts,editor=None):
    defaults=[]
    if editor:
        parent=Path(editor['path']).parent
        defaults.extend(candidate for base in (parent,parent.parent,parent.parent.parent)
                        if (candidate:=base/'JianyingPro Drafts').is_dir())
    defaults.append(Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'JianyingPro'/'User Data'/'Projects'/'com.lveditor.draft')
    roots=([Path(opts['draftRoot'])] if opts['draftRoot'] else [])+defaults
    return list(dict.fromkeys(str(p.expanduser().resolve()) for p in roots))

def status(opts=None):
    opts=options(opts)
    candidates=[opts['executable']] if opts['executable'] else _editor_candidates()
    editor=next((item for p in candidates if (item:=_verified_editor(p))),None)
    try:version=importlib.metadata.version('pyJianYingDraft')
    except importlib.metadata.PackageNotFoundError:version=''
    roots=_draft_roots(opts,editor)
    note=('草稿使用第三方格式桥接，不是官方API。需在剪映实际打开工程后，从官方编辑器界面获取截图；启动软件或复制草稿不代表工程已打开。' if editor else
          '未检测到版本信息及官方有效数字签名均通过的 JianyingPro.exe。请安装官方剪映或选择其主程序；未知发行者不会自动启动。已有草稿目录不代表已安装剪映。')
    if not editor and opts['executable']:
        note=_EDITOR_DIAGNOSTICS.get(str(Path(opts['executable']).expanduser().resolve()),note)
    return {'available':bool(version),'component':'pyJianYingDraft','version':version,'editorInstalled':bool(editor),
            'editorState':'installed' if editor else 'invalid_executable' if opts['executable'] else 'not_installed',
            'editorExecutable':editor['path'] if editor else '', 'editorVersion':editor['version'] if editor else '',
            'editorProduct':editor['product'] if editor else '', 'editorMetadataVerified':bool(editor),
            'editorSignatureVerified':bool(editor),'editorSignaturePublisher':editor.get('signaturePublisher','') if editor else '',
            'draftRoot':roots[0],'draftRoots':roots,
            'draftRootExists':Path(roots[0]).is_dir(),'editorValidated':False,
            'note':note}

def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block:=stream.read(2*1024*1024):digest.update(block)
    return digest.hexdigest()

def cancelled(event):
    if event.is_set():raise InterruptedError('剪映工程导出已停止，已完成工程保留')

def generate(video,analysis,root,ffmpeg,run,event,notify=lambda *a:None,opts=None):
    import pyJianYingDraft as draft
    opts=options(opts)
    jianying_timeline.validate_snapshots(video)
    additional=jianying_timeline.input_snapshots(video,opts)
    cancelled(event);root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    source=Path(video['path']).resolve();stat=source.stat()
    if shutil.disk_usage(root).free<stat.st_size+sum(v["bytes"] for v in additional.values())+256*1024**2:raise ValueError('工程目录空间不足，需要容纳原片及音轨')
    safe=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',source.stem).strip(' .')[:60] or '视频'
    name=safe+'_'+time.strftime('%Y%m%d-%H%M%S')+'_'+uuid.uuid4().hex[:6]
    folder=root/name
    script=draft.DraftFolder(str(root)).create_draft(name,video['width'],video['height'],30,maintrack_adsorb=False)
    incomplete=folder/'未完成工程.txt';incomplete.write_text('尚未完成素材校验，请勿导入剪映。','utf-8')
    resources=folder/'Resources';resources.mkdir();assets=[]
    try:
        notify('copy',0,stat.st_size);target=resources/('video'+source.suffix.lower());digest=hashlib.sha256();done=0
        with source.open('rb') as src,target.open('xb') as dst:
            while block:=src.read(2*1024*1024):
                cancelled(event);dst.write(block);digest.update(block);done+=len(block);notify('copy',done,stat.st_size)
        if (source.stat().st_size,source.stat().st_mtime_ns)!=(stat.st_size,stat.st_mtime_ns):raise ValueError('复制期间原片发生变化')
        if digest.hexdigest()!=analysis['sourceSHA256']:raise ValueError('源片与镜头分析不匹配，请重新导出')
        assets.append({'relative':target.relative_to(folder).as_posix(),'sha256':digest.hexdigest(),'bytes':done})
        material=draft.VideoMaterial(str(target),material_name=source.name)
        duration=min(round(video['duration']*1e6),material.duration)
        script.append_tracks([draft.TrackSpec(draft.TrackType.video,'画面剪辑')])
        ranges=jianying_timeline.ranges(analysis['segments'],duration,opts)
        for index,item in enumerate(ranges):
            cancelled(event);notify('timeline',index,len(ranges))
            span=draft.Timerange(item['start'],item['duration'])
            clip=draft.VideoSegment(material,span,source_timerange=span,volume=0 if video.get('audio') else 1)
            if opts['timelineMode']=='detailed' and opts['cameraMotion']:
                start_scale,end_scale=(1.0,1.035) if index%2==0 else (1.035,1.0)
                clip.add_keyframe(draft.KeyframeProperty.uniform_scale,0,start_scale)
                clip.add_keyframe(draft.KeyframeProperty.uniform_scale,max(1,item['duration']-1),end_scale)
            script.add_segment(clip,'画面剪辑')
        notify('timeline',len(ranges),len(ranges))
        timeline=jianying_timeline.add_tracks(draft,script,video,resources,assets,ranges,duration,opts,ffmpeg,run,event,notify)
        cancelled(event);notify('draft',0,1);script.save()
        content=folder/'draft_content.json';data=json.loads(content.read_text('utf-8'))
        if data['duration']>duration+50000:raise ValueError('同名字幕超出视频时长，请先核对 SRT 时间码')
        meta_file=folder/'draft_meta_info.json';meta=json.loads(meta_file.read_text('utf-8'))
        meta.update(draft_id=data['id'],draft_name=name,draft_fold_path=str(folder),draft_root_path=str(root),tm_duration=duration)
        meta_file.write_text(json.dumps(meta,ensure_ascii=False,indent=2),'utf-8')
        manifest={'format':1,'product':'ManjuStudio','kind':'jianying_project','name':name,'sourceName':source.name,'sourceSHA256':digest.hexdigest(),
                  'durationUs':duration,'ranges':ranges,'tracks':[{'name':t.get('name'),'type':t['type'],'segments':len(t.get('segments',[]))} for t in data['tracks']],
                  'assets':assets,'timeline':timeline,'draftSHA256':sha(content),'editorValidated':False,'createdAt':time.time(),'component':status()['version'],
                  'note':'重新剪辑的实际工程。素材已复制到 Resources；移动目录后需要在工具内重新定位素材，或在剪映手动重连。'}
        index=folder/'manju_project.json';index.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf-8')
        check(folder);cancelled(event);incomplete.unlink();notify('draft',1,1)
        return {'directory':str(folder),'path':str(content),'manifest':str(index),'name':name,'duration':duration/1e6,'tracks':len(data['tracks']),
                'segments':len(ranges),'timeline':timeline,'warnings':timeline['warnings'],'sourceSHA256':digest.hexdigest(),'draftSHA256':sha(content),'manifestSHA256':sha(index),'editorValidated':False}
    except BaseException:
        # Keep incomplete work visible for diagnosis, never mark it as completed.
        raise

def check(folder,*,validate_paths=True):
    folder=Path(folder).resolve();index=json.loads((folder/'manju_project.json').read_text('utf-8'))
    if index.get('product')!='ManjuStudio' or index.get('kind')!='jianying_project':raise ValueError('不是本工具导出的剪映工程')
    for item in index['assets']:
        path=(folder/item['relative']).resolve()
        if not path.is_relative_to(folder) or not path.is_file() or sha(path)!=item['sha256']:raise ValueError('工程素材缺失或校验失败')
    if sha(folder/'draft_content.json')!=index['draftSHA256']:raise ValueError('草稿内容已变化，请在剪映核对后重新登记')
    if validate_paths and index.get('timeline'):
        jianying_timeline.validate_media_paths(folder,json.loads((folder/'draft_content.json').read_text('utf-8')),index)
    return index

def relocate(folder):
    """Relink a moved, self-contained export without opening or modifying originals."""
    folder=Path(folder).resolve();index=check(folder,validate_paths=False);content=folder/'draft_content.json';data=json.loads(content.read_text('utf-8'))
    mapping={Path(a['relative']).name:str(folder/a['relative']) for a in index['assets']}
    for group in ('videos','audios'):
        for material in data.get('materials',{}).get(group,[]):
            old=material.get('path','');name=Path(old).name
            if name in mapping:material['path']=mapping[name]
    backup=content.with_suffix('.before-relink.json')
    if not backup.exists():shutil.copy2(content,backup)
    content.write_text(json.dumps(data,ensure_ascii=False,indent=2),'utf-8');index['draftSHA256']=sha(content)
    (folder/'manju_project.json').write_text(json.dumps(index,ensure_ascii=False,indent=2),'utf-8')
    meta=folder/'draft_meta_info.json';value=json.loads(meta.read_text('utf-8'));value.update(draft_fold_path=str(folder),draft_root_path=str(folder.parent));meta.write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf-8')
    check(folder);return {'directory':str(folder),'relinked':True}

def _safe_draft_root(value):
    root=Path(value).expanduser().resolve()
    if not root.is_absolute() or root==Path(root.anchor) or root.name in ('Windows','System32'):
        raise ValueError('请选择剪映的独立草稿目录，不能选择系统根目录')
    return root

def install_to_editor(folder,opts=None,*,operation_id=None):
    """Stage a fresh copy in the editor draft root, without changing its index.

    The editor still has to discover and open this draft. A copy cannot be used
    as evidence that Jianying accepted the content or generated a screenshot.
    """
    opts=options(opts);source=Path(folder).expanduser().resolve();index=check(source)
    if (source/'未完成工程.txt').exists():raise ValueError('工程尚未完成校验，不能导入剪映')
    root=_safe_draft_root(status(opts)['draftRoot'])
    if root==source or root.is_relative_to(source):raise ValueError('剪映草稿目录不能放在源工程内部')
    files=['draft_content.json','draft_meta_info.json','manju_project.json']
    names=[]
    for asset in index['assets']:
        relative=Path(asset['relative']);path=(source/relative).resolve()
        if relative.is_absolute() or not path.is_relative_to(source) or not path.is_file():raise ValueError('工程素材路径越界或缺失')
        if relative.name.casefold() in names:raise ValueError('工程存在重名素材，请先整理后导入')
        names.append(relative.name.casefold());files.append(relative.as_posix())
    required=sum((source/name).stat().st_size for name in files)
    root.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(root).free<required+64*1024**2:raise ValueError('剪映草稿磁盘空间不足')
    safe=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',index.get('name') or source.name).strip(' .')[:80] or '漫剧工程'
    with _IMPORT_LOCK:
        if operation_id:
            if not isinstance(operation_id,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',operation_id):raise ValueError('工程交接编号无效')
            name=safe+'_流程_'+operation_id
        else:name=safe+'_导入_'+time.strftime('%Y%m%d-%H%M%S')+'_'+uuid.uuid4().hex[:6]
        target=root/name
        if target.exists() and operation_id:
            if (target/'未完成导入.txt').exists():raise ValueError('上次工程复制中断，请先核对并移走该未完成草稿：'+str(target))
            saved,_=_open_index(target)
            if saved.get('flowOperationId')!=operation_id or saved.get('importedFrom')!=str(source):raise ValueError('工程交接目录已被其他文件占用')
            return {'directory':str(target),'name':name,'path':str(target/'draft_content.json'),'manifest':str(target/'manju_project.json'),
                    'draftRoot':str(root),'editorValidated':False,'indexModified':False,'reused':True}
        target.mkdir()
    marker=target/'未完成导入.txt';marker.write_text('素材尚未校验完成，请勿打开。','utf-8')
    for relative in files:
        src=source/relative;dst=target/relative
        dst.parent.mkdir(parents=True,exist_ok=True)
        with src.open('rb') as stream,dst.open('xb') as output:shutil.copyfileobj(stream,output,2*1024**2)
    # Check copied bytes before modifying the copied draft's own paths and IDs.
    copied=check(target)
    relocate(target)
    content=target/'draft_content.json';draft=json.loads(content.read_text('utf-8'))
    draft['id']=str(uuid.uuid4()).upper()
    content.write_text(json.dumps(draft,ensure_ascii=False,indent=2),'utf-8')
    meta_file=target/'draft_meta_info.json';meta=json.loads(meta_file.read_text('utf-8'))
    meta.update(draft_id=draft['id'],draft_name=name,draft_fold_path=str(target),draft_root_path=str(root))
    meta_file.write_text(json.dumps(meta,ensure_ascii=False,indent=2),'utf-8')
    manifest=target/'manju_project.json';copied.update(name=name,draftSHA256=sha(content),
        editorValidated=False,editorImportedAt=time.time(),importedFrom=str(source),editorMetaSHA256=sha(meta_file),
        note='草稿已复制并重定位，尚未验证剪映实际打开；不是官方API导入回执。')
    if operation_id:copied['flowOperationId']=operation_id
    manifest.write_text(json.dumps(copied,ensure_ascii=False,indent=2),'utf-8')
    check(target);marker.unlink()
    return {'directory':str(target),'name':name,'path':str(content),'manifest':str(manifest),
            'draftRoot':str(root),'editorValidated':False,'indexModified':False,
            'note':'已放入草稿目录。请在剪映草稿列表查找该工程并实际打开；列表未出现时，请按当前剪映版本使用导入或本地草稿入口。'}

def _open_index(folder):
    """Verify our inventory, allowing native changes only in an imported copy.

    This does not parse, rewrite, or try to decrypt the editor-owned draft data.
    Resources listed in our inventory remain protected by their original hash.
    """
    manifest=folder/'manju_project.json'
    if not manifest.resolve().is_relative_to(folder) or not manifest.is_file() or manifest.stat().st_size>10*1024**2:
        raise ValueError('剪映工程清单缺失或无效')
    index=json.loads(manifest.read_text('utf-8'))
    if not isinstance(index,dict) or index.get('product')!='ManjuStudio' or index.get('kind')!='jianying_project':
        raise ValueError('不是本工具登记的剪映工程')
    assets=index.get('assets')
    if not isinstance(assets,list) or not assets or len(assets)>10000:raise ValueError('工程素材清单无效')
    for asset in assets:
        if not isinstance(asset,dict) or not isinstance(asset.get('relative'),str) or not re.fullmatch(r'[a-f0-9]{64}',str(asset.get('sha256',''))):
            raise ValueError('工程素材条目无效')
        relative=Path(asset['relative']);path=(folder/relative).resolve()
        if relative.is_absolute() or not path.is_relative_to(folder) or not path.is_file() or sha(path)!=asset['sha256']:
            raise ValueError('工程素材缺失、越界或校验失败')
    content=folder/'draft_content.json'
    if not content.resolve().is_relative_to(folder) or not content.is_file() or not re.fullmatch(r'[a-f0-9]{64}',str(index.get('draftSHA256',''))):
        raise ValueError('工程草稿文件缺失或无效')
    changed=sha(content)!=index['draftSHA256']
    meta=folder/'draft_meta_info.json'
    if index.get('editorMetaSHA256'):
        if not meta.resolve().is_relative_to(folder) or not meta.is_file():raise ValueError('工程元信息缺失或越界')
        changed=changed or sha(meta)!=index['editorMetaSHA256']
    imported_at=index.get('editorImportedAt')
    imported=(type(imported_at) in (int,float) and 0<imported_at<=time.time()+60 and
              isinstance(index.get('importedFrom'),str) and Path(index['importedFrom']).is_absolute())
    if changed and not imported:raise ValueError('原始生成工程内容已变化，请重新导出或核对；不会将其冒充已登记的编辑器副本')
    if not changed and index.get('timeline'):
        jianying_timeline.validate_media_paths(folder,json.loads(content.read_text('utf-8')),index)
    return index,changed

def open_in_editor(folder,opts=None):
    """Launch the validated editor. It deliberately claims no selected project."""
    opts=options(opts);folder=Path(folder).expanduser().resolve();index,modified=_open_index(folder)
    if (folder/'未完成工程.txt').exists() or (folder/'未完成导入.txt').exists():raise ValueError('工程尚未完成，不能打开')
    current=status(opts)
    if not current['editorInstalled']:raise ValueError(current['note'])
    exe=Path(current['editorExecutable'])
    # No shell, URI scheme, downloaded binary, or undocumented draft argument.
    process=subprocess.Popen([str(exe)],cwd=str(exe.parent),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    return {'appLaunched':True,'projectOpened':False,'editorValidated':False,'editorModified':modified,'directory':str(folder),
            'name':index.get('name',folder.name),'editorExecutable':str(exe),'pid':process.pid,
            'note':'已启动剪映。请在草稿列表打开「'+str(index.get('name',folder.name))+'」，确认时间线和预览正常后再获取官方界面截图。'}
