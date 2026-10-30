"""Build editable cuts, captions and sound tracks from inventoried local media."""
from pathlib import Path
import hashlib
import math
import re
import json
import random
import bisect
import jianying_ai
import jianying_editing


DEFAULTS = {'timelineMode':'detailed','shotSeconds':10,'cameraMotion':True,
            'originalVolume':1.0,'subtitlePath':'','subtitleStyle':'bold',
            'musicPath':'','musicVolume':0.15,'soundEffectPath':'','soundEffectVolume':0.35,
            'soundEffectEvery':4,'mouseOpen':False,
            'editProfile':'cinema','colorAdjust':True,'cutMaterials':True,'speedPattern':'original',
            'transition':'dissolve','filterStyle':'cinema','filterIntensity':25,'visualEffect':'','overlayText':'',
            'audioMode':'separate','captionMode':'auto','aiPython':'','aiModelRoot':'','aiDevice':'auto',
            'aiFailure':'keep','cudaLibraries':'auto','asrLanguage':'zh','separationModel':'htdemucs','captionLength':14,
            'materialLibrary':'','mood':'auto','addBgm':False,'adjustTrack':True,'duckMusic':True,'registerIndex':True,'timelineZoom':2,'previewBeforeCapture':False}
AUDIO_EXT = {'.mp3','.wav','.m4a','.aac','.flac','.ogg','.opus','.wma'}


def options(value):
    out=DEFAULTS|{'addBgm':bool(value.get('musicPath'))}|value
    if out['timelineMode'] not in ('basic','detailed'):raise ValueError('请选择基础工程或完整剪辑工程')
    if out['subtitleStyle'] not in ('plain','bold','yellow'):raise ValueError('字幕样式无效')
    for key,choices in {'editProfile':set(jianying_editing.PROFILES),'speedPattern':{'original','gentle'},
                        'transition':{'none','dissolve'},'filterStyle':{'none','cinema'},'audioMode':{'original','separate'},
                        'captionMode':{'srt','auto','none'},'aiDevice':{'auto','cpu'},'aiFailure':{'keep','stop'},'cudaLibraries':{'auto','torch','nvidia'},
                        'asrLanguage':{'','zh','en','ja','ko'},'separationModel':{'htdemucs','htdemucs_ft','mdx_extra'},
                        'mood':{'auto',*jianying_editing.MOODS},'visualEffect':{'','_1998','_70s'}}.items():
        if not isinstance(out[key],str) or out[key] not in choices:raise ValueError('剪映工程选项无效：'+key)
    for name in ('cameraMotion','mouseOpen','colorAdjust','cutMaterials','addBgm','adjustTrack','duckMusic','registerIndex','previewBeforeCapture'):
        if type(out[name]) is not bool:raise ValueError('剪映自动化选项无效')
    labels={'shotSeconds':'单片段最长秒数','originalVolume':'原声音量','musicVolume':'背景音乐音量','soundEffectVolume':'音效音量','filterIntensity':'滤镜强度'}
    for name,low,high in [('shotSeconds',2,30),('originalVolume',0,2),('musicVolume',0,1),('soundEffectVolume',0,1),('filterIntensity',0,100)]:
        n=out[name]
        if type(n) not in (int,float) or not math.isfinite(n) or not low<=n<=high:raise ValueError(labels[name]+'应在'+str(low)+'至'+str(high)+'之间')
    if type(out['soundEffectEvery']) is not int or not 1<=out['soundEffectEvery']<=30:raise ValueError('音效间隔应为1至30个片段')
    if type(out['captionLength']) is not int or not 6<=out['captionLength']<=30:raise ValueError('字幕每行字数应为6至30')
    if type(out['timelineZoom']) is not int or not 0<=out['timelineZoom']<=5:raise ValueError('时间线放大步数应为0至5')
    if not isinstance(out['overlayText'],str) or len(out['overlayText'])>50 or any(ord(c)<32 for c in out['overlayText']):raise ValueError('角标文字最多50字')
    for name in ('subtitlePath','musicPath','soundEffectPath','aiPython','aiModelRoot','materialLibrary'):
        path=out[name]
        if not isinstance(path,str) or len(path)>2000 or any(ord(c)<32 for c in path):raise ValueError('剪映素材路径无效')
        if path and not Path(path).is_absolute():raise ValueError('请选择本机素材的绝对路径')
    return out


def input_snapshots(video,opts):
    paths=[]
    subtitle=Path(opts['subtitlePath']) if opts['subtitlePath'] else Path(video['path']).with_suffix('.srt')
    if opts['captionMode']!='none' and (opts['subtitlePath'] or subtitle.is_file()):paths.append((subtitle,{'.srt'},'字幕'))
    for key,label in [('musicPath','背景音乐'),('soundEffectPath','音效')]:
        if key=='musicPath' and not opts['addBgm']:continue
        if opts[key]:paths.append((Path(opts[key]),AUDIO_EXT,label))
    for files in video.get('jianyingLibraryFiles',{}).values():paths.extend((Path(p),AUDIO_EXT,'剪映声音素材') for p in files)
    result={}
    for path,allowed,label in paths:
        if path.suffix.lower() not in allowed or not path.is_file():raise ValueError(label+'文件不可读取，请重新选择')
        stat=path.stat()
        if stat.st_size<=0 or (label=='字幕' and stat.st_size>10*1024**2):raise ValueError(label+'文件为空或超过大小限制')
        result[str(path.resolve())]={'bytes':stat.st_size,'mtime':stat.st_mtime_ns}
    return result


def validate_snapshots(video):
    for name,expected in video.get('jianyingAssets',{}).items():
        path=Path(name)
        if not path.is_file():raise ValueError('排队期间字幕或音频素材已移走，请重新选择后创建任务')
        stat=path.stat()
        if expected!={'bytes':stat.st_size,'mtime':stat.st_mtime_ns}:raise ValueError('排队期间字幕或音频素材已变化，请重新创建任务')


def file_hash(path,event):
    digest=hashlib.sha256()
    with path.open('rb') as reader:
        while block:=reader.read(2*1024**2):
            if event.is_set():raise InterruptedError('工程导出已停止')
            digest.update(block)
    return digest.hexdigest()


def ranges(segments,duration,opts,*,seed=''):
    scenes=[]
    for item in segments:
        a,b=float(item['start']),float(item['end'])
        if not math.isfinite(a) or not math.isfinite(b):raise ValueError('分镜时间码无效')
        start=max(0,round(a*1e6));end=min(duration,round(b*1e6))
        if end>start:scenes.append({'start':start,'duration':end-start,'sourceStart':start})
    if not scenes or scenes[0]['start']!=0 or scenes[-1]['start']+scenes[-1]['duration']!=duration:
        raise ValueError('视频分段未覆盖完整时间线')
    if any(a['start']+a['duration']!=b['start'] for a,b in zip(scenes,scenes[1:])):raise ValueError('时间线存在间隙或重叠')
    result=scenes if opts['timelineMode']!='detailed' else bounded_cuts(scenes,duration,round(opts['shotSeconds']*1e6),seed)
    if len(result)>5000:raise ValueError('剪辑片段超过5000个，请增大片段时长或分批处理')
    cursor=0
    for i,item in enumerate(result):
        source_duration=item['duration']
        speed=(.98,1.02,1.)[i%3] if opts['speedPattern']=='gentle' and opts['timelineMode']=='detailed' else 1.
        item.update(start=cursor,sourceDuration=source_duration,duration=round(source_duration/speed))
        cursor+=item['duration']
    return result


def bounded_cuts(scenes,duration,maximum,seed):
    """Seeded lengths with complete coverage; nearby scene cuts are soft anchors."""
    minimum=2000000
    if duration<minimum:return [{'start':0,'duration':duration,'sourceStart':0}]
    least=(duration+maximum-1)//maximum;most=min(5000,duration//minimum)
    if least>5000:raise ValueError('剪辑片段超过5000个，请增大片段时长或分批处理')
    if least>most:raise ValueError('当前视频时长无法同时满足至少2秒和所设最长秒数，请提高单片段最长秒数')
    rng=random.Random(str(seed))
    target=rng.uniform(minimum+(maximum-minimum)*.35,minimum+(maximum-minimum)*.65)
    count=max(least,min(most,math.floor(duration/target+.5)))
    anchors=[s['start'] for s in scenes[1:]]
    result=[];start=0
    for remaining in range(count,0,-1):
        left=duration-start
        if remaining==1:stop=duration
        else:
            # Reserve enough time for every remaining cut, including the tail.
            low=max(minimum,left-(remaining-1)*maximum)
            high=min(maximum,left-(remaining-1)*minimum)
            stop=start+rng.randint(low,high)
            position=bisect.bisect_left(anchors,stop)
            nearby=[x for x in anchors[max(0,position-1):position+1]
                    if start+low<=x<=start+high and abs(x-stop)<=650000]
            if nearby:stop=min(nearby,key=lambda x:abs(x-stop))
        result.append({'start':start,'duration':stop-start,'sourceStart':start})
        start=stop
    return result


def copy_asset(source,resources,name,video,event,notify):
    source=Path(source).resolve();stat=source.stat()
    expected=video.get('jianyingAssets',{}).get(str(source))
    if expected and expected!={'bytes':stat.st_size,'mtime':stat.st_mtime_ns}:raise ValueError('排队期间工程附加素材发生变化，请重新创建任务')
    target=resources/name;digest=hashlib.sha256();done=0
    notify('assets',0,stat.st_size)
    with source.open('rb') as reader,target.open('xb') as writer:
        while block:=reader.read(2*1024**2):
            if event.is_set():raise InterruptedError('工程导出已停止')
            writer.write(block);digest.update(block);done+=len(block);notify('assets',done,stat.st_size)
    if (source.stat().st_size,source.stat().st_mtime_ns)!=(stat.st_size,stat.st_mtime_ns):raise ValueError('复制期间工程附加素材发生变化')
    return target,{'relative':target.relative_to(resources.parent).as_posix(),'sha256':digest.hexdigest(),'bytes':done}


def read_captions(path,duration):
    try:text=path.read_text('utf-8-sig').replace('\r\n','\n').strip()
    except UnicodeError:raise ValueError('字幕文件编码无法读取，请保存为 UTF-8 SRT 后重试') from None
    stamp=r'(\d{1,3}):(\d{2}):(\d{2})[,.](\d{3})'
    def micro(groups):
        h,m,s,ms=map(int,groups)
        if m>=60 or s>=60:raise ValueError('SRT 时间码无效')
        return ((h*60+m)*60+s)*1_000_000+ms*1000
    result=[]
    for block in re.split(r'\n[ \t]*\n',text):
        lines=block.splitlines()
        if len(lines)<3 or not lines[0].strip().isdigit():raise ValueError('SRT 格式无效，请提供带序号和时间码的 UTF-8 字幕')
        match=re.fullmatch(stamp+r'\s*-->\s*'+stamp,lines[1].strip())
        if not match:raise ValueError('SRT 时间码无效：第'+lines[0]+'条')
        start,end=micro(match.groups()[:4]),micro(match.groups()[4:])
        if end>duration+50000 or start>=duration:raise ValueError('字幕超出本集时长，请核对字幕与视频是否对应')
        if end<=start or (result and start<result[-1]['end']):raise ValueError('字幕时间码重叠或倒置，请核对第'+lines[0]+'条')
        content=re.sub(r'</?(?:i|b|u|font)(?:\s[^>]*)?>','','\n'.join(lines[2:]).strip(),flags=re.I)
        if content:result.append({'start':start,'end':min(end,duration),'text':content})
        if len(result)>10000:raise ValueError('字幕条数超过10000，请分批处理')
    if not result:raise ValueError('字幕文件没有可导入的文字')
    return result


def append_audio(draft,script,material,name,clips,volume,fade=False,speech=None):
    if not clips:return 0
    script.append_tracks([draft.TrackSpec(draft.TrackType.audio,name)])
    for item in clips:
        start,length,source_start=item[:3];source_length=item[3] if len(item)==4 else length
        segment=draft.AudioSegment(material,draft.Timerange(start,length),
                                   source_timerange=draft.Timerange(source_start,source_length),volume=volume)
        if fade:
            ramp=min(800000,length//4);segment.add_fade(ramp,ramp)
        if speech:
            points={0:volume,max(0,length-1):volume}
            for a,b in speech:
                left=max(0,a-start);right=min(length-1,b-start)
                if right<=left:continue
                points[max(0,left-150000)]=volume
                points[left]=volume*.35;points[right]=volume*.35
                points[min(length-1,right+220000)]=volume
            for offset,gain in sorted(points.items()):segment.add_keyframe(offset,gain)
        script.add_segment(segment,name)
    return len(clips)


def add_tracks(draft,script,video,resources,assets,cuts,duration,opts,ffmpeg,run,event,notify,source_duration=None):
    source_duration=source_duration or duration
    result={'mode':opts['timelineMode'],'videoSegments':len(cuts),'originalSegments':0,
            'captionSegments':0,'musicSegments':0,'soundEffectSegments':0,
            'motionSegments':len(cuts) if opts['timelineMode']=='detailed' and opts['cameraMotion'] else 0,'warnings':[]}
    subtitle=Path(opts['subtitlePath']) if opts['subtitlePath'] else Path(video['path']).with_suffix('.srt')
    has_srt=opts['captionMode']!='none' and subtitle.is_file()
    ai={'stems':[],'cues':[],'warnings':[],'separation':'disabled','asr':'disabled','devices':{}}
    speech=[];source_speech=[]
    if video.get('audio'):
        notify('audio',0,1);audio=resources/'原声.wav'
        run([str(ffmpeg),'-hide_banner','-loglevel','error','-nostdin','-y','-i',str(resources/('video'+Path(video['path']).suffix.lower())),
             '-vn','-ac','2','-ar','44100','-c:a','pcm_s16le','-t',str(source_duration/1e6),str(audio)],timeout=600)
        material=draft.AudioMaterial(str(audio));end=min(duration,material.duration)
        if end<=0:raise ValueError('原声音轨时长无法读取，请核对输入视频')
        if abs(material.duration-source_duration)>150000:raise ValueError('原声音频与画面时长不一致，请核对输入视频')
        if opts['timelineMode']=='detailed':ai=jianying_ai.prepare(audio,resources,source_duration,opts,run,event,notify,not has_srt)
        result['warnings']+=ai['warnings'];result['ai']={k:v for k,v in ai.items() if k not in ('stems','cues','warnings')}
        active_audio=ai['stems'][0] if ai['stems'] else audio
        source_speech=jianying_editing.activity(active_audio,event)
        for x,y in source_speech:
            for a,n,_,_ in jianying_editing.mapped_intervals(x,y,cuts):
                if speech and a<=speech[-1][1]+370000:speech[-1]=(speech[-1][0],a+n)
                else:speech.append((a,a+n))
        if ai['stems']:
            for path,label in zip(ai['stems'],('人声','背景声')):
                stem=draft.AudioMaterial(str(path));clips=[]
                # Split at measured voice activity boundaries without deleting
                # quiet dialogue or silence from the reconstructed source.
                boundaries=sorted({0,source_duration,*[min(source_duration,max(0,x)) for span in source_speech for x in span]})
                spans=list(zip(boundaries,boundaries[1:])) if label=='人声' else [(0,source_duration)]
                for a,b in spans:clips.extend(jianying_editing.mapped_intervals(a,min(b,stem.duration),cuts))
                if len(clips)>10000:raise ValueError('分离音轨超过10000段，请分集处理')
                if label=='背景声' and len(clips)>=4:
                    # Both native reference projects partition one background
                    # WAV across two tracks. Each interval is used once.
                    seed=assets[0]['sha256']
                    secondary=set(sorted(range(len(clips)),key=lambda i:hashlib.sha256((seed+':background:'+str(i)).encode()).hexdigest())[:max(1,len(clips)//8)])
                    primary_clips=[clip for i,clip in enumerate(clips) if i not in secondary]
                    secondary_clips=[clip for i,clip in enumerate(clips) if i in secondary]
                    count=append_audio(draft,script,stem,label,primary_clips,opts['originalVolume'])
                    count+=append_audio(draft,script,stem,'背景声2',secondary_clips,opts['originalVolume'])
                    result['backgroundTracks']=2;result['auxiliaryBackgroundSegments']=len(secondary_clips)
                else:count=append_audio(draft,script,stem,label,clips,opts['originalVolume'])
                result['vocalSegments' if label=='人声' else 'backgroundSegments']=count
                assets.append({'relative':path.relative_to(resources.parent).as_posix(),'sha256':file_hash(path,event),'bytes':path.stat().st_size})
        else:
            clips=list(jianying_editing.mapped_intervals(0,min(material.duration,source_duration),cuts))
            if opts['timelineMode']=='basic':clips=[(0,min(material.duration,source_duration),0)]
            result['originalSegments']=append_audio(draft,script,material,'混合原声',clips,opts['originalVolume'])
        assets.append({'relative':audio.relative_to(resources.parent).as_posix(),'sha256':file_hash(audio,event),'bytes':audio.stat().st_size})
        notify('audio',1,1)
    else:result['warnings'].append('输入视频没有音轨，未生成原声轨')
    pools={}
    if video.get('jianyingLibraryFiles') is not None:
        frozen=video['jianyingLibraryFiles']
        pools={'musicPath':[Path(p) for p in frozen['bgm']],'soundEffectPath':[Path(p) for p in frozen['sfx']]}
        result['materialSelection']=video.get('jianyingMaterialReport',{})|{'bgmEnabled':opts['addBgm']}
        if not opts['soundEffectPath'] and not pools['soundEffectPath']:
            result['warnings'].append('剪映缓存中未找到可用短音效，本集不添加音效；下载音效后可用于后续工程')
    elif opts['materialLibrary']:
        for kind,key in [('bgm','musicPath'),('sfx','soundEffectPath')]:
            folder=Path(opts['materialLibrary'])/kind
            files=jianying_editing.library_files(folder) if folder.is_dir() else []
            if video.get('jianyingAssets') is not None:files=[p for p in files if str(p.resolve()) in video['jianyingAssets']]
            pools[key]=jianying_editing.select_materials(files,video.get('projectName','')+' '+video['name'],opts['mood'],1 if kind=='bgm' else 8)
            if not files and not opts[key]:result['warnings'].append('素材库 '+kind+' 没有可用音频，未添加对应轨道')
    for key,label in [('musicPath','背景音乐'),('soundEffectPath','转场音效')]:
        if key=='musicPath' and not opts['addBgm']:continue
        sources=[Path(opts[key])] if opts[key] else pools.get(key,[])
        if not sources:continue
        if event.is_set():raise InterruptedError('工程导出已停止')
        count=0
        for asset_index,source in enumerate(sources):
            target,entry=copy_asset(source,resources,label+str(asset_index+1)+source.suffix.lower(),video,event,notify);assets.append(entry)
            material=draft.AudioMaterial(str(target))
            if material.duration<=0:raise ValueError(label+'没有可读取的音频时长')
            clips=[]
            if key=='musicPath':
                start=0
                while start<duration:
                    length=min(material.duration,duration-start);clips.append((start,length,0));start+=length
                    if len(clips)>5000:raise ValueError('配乐过短，请选择更长的背景音乐')
            else:
                selected=cuts[1::opts['soundEffectEvery']][asset_index::len(sources)]
                clips=[(r['start'],min(material.duration,r['duration'],2_000_000),0) for r in selected]
            count+=append_audio(draft,script,material,label+str(asset_index+1),clips,opts['musicVolume'] if key=='musicPath' else opts['soundEffectVolume'],True,speech if key=='musicPath' and opts['duckMusic'] else None)
        result['musicSegments' if key=='musicPath' else 'soundEffectSegments']=count
        if not count:result['warnings'].append('当前只有一个画面片段，未添加转场音效')
    cues=ai['cues']
    if has_srt:
        caption,entry=copy_asset(subtitle,resources,'字幕.srt',video,event,notify);assets.append(entry)
        cues=read_captions(caption,source_duration)
    if cues:
        cues=jianying_editing.captions(cues,source_speech if ai['stems'] else [],cuts)
        if not has_srt:
            generated=resources/'识别字幕.json';generated.write_text(json.dumps(cues,ensure_ascii=False),'utf-8')
            assets.append({'relative':generated.relative_to(resources.parent).as_posix(),'sha256':file_hash(generated,event),'bytes':generated.stat().st_size})
        notify('captions',0,len(cues))
        style=draft.TextStyle(size=9 if opts['subtitleStyle']!='plain' else 6,bold=opts['subtitleStyle']!='plain',
                              align=1,auto_wrapping=True,max_line_width=0.82,
                              color=(1.0,0.87,0.12) if opts['subtitleStyle']=='yellow' else (1.0,1.0,1.0))
        script.append_tracks([draft.TrackSpec(draft.TrackType.text,'字幕')])
        for index,cue in enumerate(cues):
            if event.is_set():raise InterruptedError('工程导出已停止')
            clip=draft.TextSegment(cue['text'],draft.Timerange(cue['start'],cue['end']-cue['start']),style=style,
                                  border=draft.TextBorder(width=32),clip_settings=draft.ClipSettings(transform_y=-0.73))
            script.add_segment(clip,'字幕');notify('captions',index+1,len(cues))
        result['captionSegments']=len(cues)
    elif opts['captionMode']!='none':result['warnings'].append('没有可用 SRT 或识别文字，未生成可编辑字幕；画面中的原有字幕保持原样')
    if opts['addBgm'] and not opts['musicPath'] and not pools.get('musicPath'):result['warnings'].append('已开启配乐，但剪映缓存中没有100秒以上的可用音乐，未添加配乐轨')
    return result


def validate_media_paths(folder,data,index):
    folder=Path(folder).resolve()
    inventory={(folder/a['relative']).resolve() for a in index['assets']}
    for group in ('videos','audios'):
        for material in data.get('materials',{}).get(group,[]):
            value=material.get('path')
            if not isinstance(value,str) or not value or not Path(value).is_absolute():raise ValueError('工程媒体引用不是有效本机路径，请重连素材')
            path=Path(value).resolve()
            if path not in inventory or not path.is_relative_to(folder) or not path.is_file():raise ValueError('工程存在未链接的媒体，请先重连素材再打开剪映')
    materials={str(item['id']) for values in data.get('materials',{}).values() if isinstance(values,list) for item in values if isinstance(item,dict) and item.get('id')}
    for track in data.get('tracks',[]):
        end=0
        for segment in track.get('segments',[]):
            timerange=segment.get('target_timerange',{});start=timerange.get('start');length=timerange.get('duration')
            if type(start) is not int or type(length) is not int or start<end or length<=0 or start+length>data['duration']+1000:
                raise ValueError('工程轨道时间码存在重叠、越界或空片段')
            if str(segment.get('material_id','')) not in materials:raise ValueError('工程轨道引用了未登记的素材')
            end=start+length


def validate_complete(video,opts,timeline):
    if opts['timelineMode']!='detailed' or opts['aiFailure']!='stop' or not video.get('audio'):return
    missing=[];ai=timeline.get('ai',{})
    if opts['audioMode']=='separate' and (ai.get('separation')!='completed' or not timeline.get('vocalSegments') or not timeline.get('backgroundSegments')):
        missing.append('独立人声和背景声')
    if opts['captionMode']!='none' and not timeline.get('captionSegments'):missing.append('可编辑对白字幕（没有识别到有效文字）')
    if missing:raise ValueError('完整剪映工程缺少：'+'、'.join(missing)+'；本集未记为完成，请核对引擎日志后重试')
