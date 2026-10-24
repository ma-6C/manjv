"""Editable Jianying projects from real media and measured scene intervals."""
from pathlib import Path
import hashlib,json,os,re,shutil,time,uuid,importlib.metadata

def options(value=None):
    value=value or {}
    if not isinstance(value,dict) or set(value)-{'output','splitScenes','executable'}:raise ValueError('剪映工程设置无效')
    out={'output':'','splitScenes':True,'executable':''}|value
    if type(out['splitScenes']) is not bool:raise ValueError('镜头分段设置无效')
    for name in ('output','executable'):
        if not isinstance(out[name],str) or len(out[name])>2000 or any(ord(c)<32 for c in out[name]):raise ValueError('工程路径无效')
        if out[name] and not Path(out[name]).is_absolute():raise ValueError('请选择绝对路径')
    return out

def status(opts=None):
    opts=options(opts);exe=Path(opts['executable']) if opts['executable'] else None
    try:version=importlib.metadata.version('pyJianYingDraft')
    except importlib.metadata.PackageNotFoundError:version=''
    return {'available':bool(version),'component':'pyJianYingDraft','version':version,'editorInstalled':bool(exe and exe.is_file()),
            'editorValidated':False,'note':'草稿文件可以生成；剪映打开、预览和截图需要安装编辑器后单独核验。'}

def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block:=stream.read(2*1024*1024):digest.update(block)
    return digest.hexdigest()

def cancelled(event):
    if event.is_set():raise InterruptedError('剪映工程导出已停止，已完成工程保留')

def generate(video,analysis,root,ffmpeg,run,event,notify=lambda *a:None):
    import pyJianYingDraft as draft
    cancelled(event);root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    source=Path(video['path']).resolve();stat=source.stat()
    if shutil.disk_usage(root).free<stat.st_size+256*1024**2:raise ValueError('工程目录空间不足，需要容纳原片及音轨')
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
        ranges=[]
        for segment in analysis['segments']:
            start=max(0,round(segment['start']*1e6));end=min(duration,round(segment['end']*1e6))
            if end<=start:continue
            span=draft.Timerange(start,end-start)
            script.add_segment(draft.VideoSegment(material,span,source_timerange=span,volume=0 if video.get('audio') else 1),'画面剪辑')
            ranges.append({'start':start,'duration':end-start,'sourceStart':start})
        if not ranges or ranges[0]['start']!=0 or ranges[-1]['start']+ranges[-1]['duration']!=duration:raise ValueError('视频分段未覆盖完整时间线')
        if any(a['start']+a['duration']!=b['start'] for a,b in zip(ranges,ranges[1:])):raise ValueError('时间线存在间隙或重叠')
        if video.get('audio'):
            cancelled(event);notify('audio',0,1);audio=resources/'原声.m4a'
            run([str(ffmpeg),'-hide_banner','-loglevel','error','-nostdin','-y','-i',str(target),'-vn','-c:a','aac','-b:a','192k',str(audio)],timeout=600)
            audio_material=draft.AudioMaterial(str(audio));audio_duration=min(duration,audio_material.duration)
            script.append_tracks([draft.TrackSpec(draft.TrackType.audio,'原声')]);script.add_segment(draft.AudioSegment(audio_material,draft.Timerange(0,audio_duration)),'原声')
            assets.append({'relative':audio.relative_to(folder).as_posix(),'sha256':sha(audio),'bytes':audio.stat().st_size});notify('audio',1,1)
        subtitle=source.with_suffix('.srt')
        if subtitle.is_file() and subtitle.stat().st_size<=10*1024*1024:
            cancelled(event);caption=resources/'字幕.srt';shutil.copy2(subtitle,caption)
            script.import_srt(str(caption),track_name='字幕');assets.append({'relative':caption.relative_to(folder).as_posix(),'sha256':sha(caption),'bytes':caption.stat().st_size})
        cancelled(event);notify('draft',0,1);script.save()
        content=folder/'draft_content.json';data=json.loads(content.read_text('utf-8'))
        if data['duration']>duration+50000:raise ValueError('同名字幕超出视频时长，请先核对 SRT 时间码')
        meta_file=folder/'draft_meta_info.json';meta=json.loads(meta_file.read_text('utf-8'))
        meta.update(draft_id=data['id'],draft_name=name,draft_fold_path=str(folder),draft_root_path=str(root),tm_duration=duration)
        meta_file.write_text(json.dumps(meta,ensure_ascii=False,indent=2),'utf-8')
        manifest={'format':1,'product':'ManjuStudio','kind':'jianying_project','name':name,'sourceName':source.name,'sourceSHA256':digest.hexdigest(),
                  'durationUs':duration,'ranges':ranges,'tracks':[{'name':t.get('name'),'type':t['type'],'segments':len(t.get('segments',[]))} for t in data['tracks']],
                  'assets':assets,'draftSHA256':sha(content),'editorValidated':False,'createdAt':time.time(),'component':status()['version'],
                  'note':'重新剪辑的实际工程。素材已复制到 Resources；移动目录后需要在工具内重新定位素材，或在剪映手动重连。'}
        index=folder/'manju_project.json';index.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf-8')
        check(folder);cancelled(event);incomplete.unlink();notify('draft',1,1)
        return {'directory':str(folder),'path':str(content),'manifest':str(index),'name':name,'duration':duration/1e6,'tracks':len(data['tracks']),
                'segments':len(ranges),'sourceSHA256':digest.hexdigest(),'draftSHA256':sha(content),'manifestSHA256':sha(index),'editorValidated':False}
    except BaseException:
        # Keep incomplete work visible for diagnosis, never mark it as completed.
        raise

def check(folder):
    folder=Path(folder).resolve();index=json.loads((folder/'manju_project.json').read_text('utf-8'))
    if index.get('product')!='ManjuStudio' or index.get('kind')!='jianying_project':raise ValueError('不是本工具导出的剪映工程')
    for item in index['assets']:
        path=(folder/item['relative']).resolve()
        if not path.is_relative_to(folder) or not path.is_file() or sha(path)!=item['sha256']:raise ValueError('工程素材缺失或校验失败')
    if sha(folder/'draft_content.json')!=index['draftSHA256']:raise ValueError('草稿内容已变化，请在剪映核对后重新登记')
    return index

def relocate(folder):
    """Relink a moved, self-contained export without opening or modifying originals."""
    folder=Path(folder).resolve();index=check(folder);content=folder/'draft_content.json';data=json.loads(content.read_text('utf-8'))
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
