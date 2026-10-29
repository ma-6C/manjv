"""Build editable cuts, captions and sound tracks from inventoried local media."""
from pathlib import Path
import hashlib
import math
import re


DEFAULTS = {'timelineMode':'detailed','shotSeconds':6,'cameraMotion':True,
            'originalVolume':1.0,'subtitlePath':'','subtitleStyle':'bold',
            'musicPath':'','musicVolume':0.15,'soundEffectPath':'','soundEffectVolume':0.35,
            'soundEffectEvery':4,'mouseOpen':False}
AUDIO_EXT = {'.mp3','.wav','.m4a','.aac','.flac','.ogg','.opus','.wma'}


def options(value):
    out=DEFAULTS|value
    if out['timelineMode'] not in ('basic','detailed'):raise ValueError('请选择基础工程或完整剪辑工程')
    if out['subtitleStyle'] not in ('plain','bold','yellow'):raise ValueError('字幕样式无效')
    for name in ('cameraMotion','mouseOpen'):
        if type(out[name]) is not bool:raise ValueError('剪映自动化选项无效')
    labels={'shotSeconds':'单片段最长秒数','originalVolume':'原声音量','musicVolume':'背景音乐音量','soundEffectVolume':'音效音量'}
    for name,low,high in [('shotSeconds',2,30),('originalVolume',0,2),('musicVolume',0,1),('soundEffectVolume',0,1)]:
        n=out[name]
        if type(n) not in (int,float) or not math.isfinite(n) or not low<=n<=high:raise ValueError(labels[name]+'应在'+str(low)+'至'+str(high)+'之间')
    if type(out['soundEffectEvery']) is not int or not 1<=out['soundEffectEvery']<=30:raise ValueError('音效间隔应为1至30个片段')
    for name in ('subtitlePath','musicPath','soundEffectPath'):
        path=out[name]
        if not isinstance(path,str) or len(path)>2000 or any(ord(c)<32 for c in path):raise ValueError('剪映素材路径无效')
        if path and not Path(path).is_absolute():raise ValueError('请选择本机素材的绝对路径')
    return out


def input_snapshots(video,opts):
    paths=[]
    subtitle=Path(opts['subtitlePath']) if opts['subtitlePath'] else Path(video['path']).with_suffix('.srt')
    if opts['subtitlePath'] or subtitle.is_file():paths.append((subtitle,{'.srt'},'字幕'))
    for key,label in [('musicPath','背景音乐'),('soundEffectPath','音效')]:
        if opts[key]:paths.append((Path(opts[key]),AUDIO_EXT,label))
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


def ranges(segments,duration,opts):
    result=[]
    limit=round(opts['shotSeconds']*1e6) if opts['timelineMode']=='detailed' else duration
    for item in segments:
        a,b=float(item['start']),float(item['end'])
        if not math.isfinite(a) or not math.isfinite(b):raise ValueError('分镜时间码无效')
        start=max(0,round(a*1e6));end=min(duration,round(b*1e6))
        while end>start:
            stop=min(end,start+limit)
            result.append({'start':start,'duration':stop-start,'sourceStart':start})
            start=stop
            if len(result)>5000:raise ValueError('剪辑片段超过5000个，请增大片段时长或分批处理')
    if not result or result[0]['start']!=0 or result[-1]['start']+result[-1]['duration']!=duration:
        raise ValueError('视频分段未覆盖完整时间线')
    if any(a['start']+a['duration']!=b['start'] for a,b in zip(result,result[1:])):raise ValueError('时间线存在间隙或重叠')
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


def append_audio(draft,script,material,name,clips,volume,fade=False):
    if not clips:return 0
    script.append_tracks([draft.TrackSpec(draft.TrackType.audio,name)])
    for start,length,source_start in clips:
        segment=draft.AudioSegment(material,draft.Timerange(start,length),
                                   source_timerange=draft.Timerange(source_start,length),volume=volume)
        if fade:
            ramp=min(800000,length//4);segment.add_fade(ramp,ramp)
        script.add_segment(segment,name)
    return len(clips)


def add_tracks(draft,script,video,resources,assets,cuts,duration,opts,ffmpeg,run,event,notify):
    result={'mode':opts['timelineMode'],'videoSegments':len(cuts),'originalSegments':0,
            'captionSegments':0,'musicSegments':0,'soundEffectSegments':0,
            'motionSegments':len(cuts) if opts['timelineMode']=='detailed' and opts['cameraMotion'] else 0,'warnings':[]}
    if video.get('audio'):
        notify('audio',0,1);audio=resources/'原声.m4a'
        run([str(ffmpeg),'-hide_banner','-loglevel','error','-nostdin','-y','-i',str(resources/('video'+Path(video['path']).suffix.lower())),
             '-vn','-c:a','aac','-b:a','192k',str(audio)],timeout=600)
        material=draft.AudioMaterial(str(audio));end=min(duration,material.duration)
        if end<=0:raise ValueError('原声音轨时长无法读取，请核对输入视频')
        clips=[(r['start'],min(r['duration'],end-r['start']),r['start']) for r in cuts if r['start']<end]
        if opts['timelineMode']=='basic':clips=[(0,end,0)]
        result['originalSegments']=append_audio(draft,script,material,'原声',clips,opts['originalVolume'])
        assets.append({'relative':audio.relative_to(resources.parent).as_posix(),'sha256':file_hash(audio,event),'bytes':audio.stat().st_size})
        notify('audio',1,1)
    else:result['warnings'].append('输入视频没有音轨，未生成原声轨')
    for key,label in [('musicPath','背景音乐'),('soundEffectPath','转场音效')]:
        if not opts[key]:continue
        if event.is_set():raise InterruptedError('工程导出已停止')
        source=Path(opts[key]);target,entry=copy_asset(source,resources,label+source.suffix.lower(),video,event,notify);assets.append(entry)
        material=draft.AudioMaterial(str(target))
        if material.duration<=0:raise ValueError(label+'没有可读取的音频时长')
        clips=[]
        if key=='musicPath':
            start=0
            while start<duration:
                length=min(material.duration,duration-start);clips.append((start,length,0));start+=length
                if len(clips)>5000:raise ValueError('配乐过短，请选择更长的背景音乐')
        else:
            selected=cuts[1::opts['soundEffectEvery']]
            clips=[(r['start'],min(material.duration,r['duration'],2_000_000),0) for r in selected]
        count=append_audio(draft,script,material,label,clips,opts['musicVolume'] if key=='musicPath' else opts['soundEffectVolume'],True)
        result['musicSegments' if key=='musicPath' else 'soundEffectSegments']=count
        if not count:result['warnings'].append('当前只有一个画面片段，未添加转场音效')
    subtitle=Path(opts['subtitlePath']) if opts['subtitlePath'] else Path(video['path']).with_suffix('.srt')
    if subtitle.is_file():
        caption,entry=copy_asset(subtitle,resources,'字幕.srt',video,event,notify);assets.append(entry)
        cues=read_captions(caption,duration);notify('captions',0,len(cues))
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
    else:result['warnings'].append('没有对应 SRT，未生成可编辑字幕；画面中的原有字幕保持原样')
    if not opts['musicPath']:result['warnings'].append('未选择背景音乐，保留原声剪辑')
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
