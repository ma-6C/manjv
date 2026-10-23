"""Real-frame multitrack PNG sheets. Source media is never modified."""
from __future__ import annotations
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageOps,ImageChops,ImageStat
from functools import lru_cache
import array,hashlib,json,math,os,re,shutil,threading,time,uuid,wave

VERSION=2
MAX_FILES=30
TRACKS=(3,6,7,8,9)
VIDEO_EXT={'.mp4','.mov','.mkv','.avi','.m4v','.webm','.ts'}
ANALYSIS_LOCK=threading.RLock()

def options(value):
    if not isinstance(value,dict):raise ValueError('分轨设置格式无效')
    out={'tracks':8,'device':'auto','gpuIndex':-1,'fastPng':True,'reuse':True,'width':2560,
         'sampleInterval':.75,'threshold':24.,'minScene':1.5,'maxSegment':8.,
         'output':'','naming':'original','namePrefix':'','startNumber':1,'digits':3}
    out.update({k:v for k,v in value.items() if k in out})
    if type(out['tracks']) is not int or out['tracks'] not in TRACKS:raise ValueError('轨道数请选择3、6、7、8或9')
    if out['device'] not in ('auto','cpu','gpu'):raise ValueError('识别设备请选择自动、CPU或GPU')
    if type(out['gpuIndex']) is not int or not -1<=out['gpuIndex']<=31:raise ValueError('显卡编号无效')
    if type(out['width']) is not int or out['width'] not in (1920,2560,3840):raise ValueError('图片宽度请选择1920、2560或3840')
    for k in ('fastPng','reuse'):
        if type(out[k]) is not bool:raise ValueError('请核对PNG和缓存选项')
    for k,low,high in (('sampleInterval',.25,5),('threshold',5,100),('minScene',.25,10),('maxSegment',2,60)):
        v=out[k]
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not low<=v<=high:raise ValueError('镜头分析设置超出范围')
        out[k]=float(v)
    if out['maxSegment']<out['minScene']:raise ValueError('分段最长时长不能小于最短镜头时长')
    if out['naming'] not in ('original','episode'):raise ValueError('工程图命名方式无效')
    if type(out['startNumber']) is not int or not 1<=out['startNumber']<=999999:raise ValueError('起始集号无效')
    if type(out['digits']) is not int or out['digits'] not in (2,3,4):raise ValueError('集号位数请选择2、3或4')
    for k,limit in (('output',2000),('namePrefix',60)):
        if not isinstance(out[k],str) or len(out[k])>limit or any(ord(c)<32 for c in out[k]):raise ValueError('输出位置或命名文本无效')
        out[k]=out[k].strip()
    if out['output']:
        path=Path(out['output']).expanduser()
        if not path.is_absolute() or str(path.resolve())==path.anchor:raise ValueError('请选择单独的工程图输出文件夹')
        out['output']=str(path.resolve())
    if re.search(r'[<>:"/\\|?*]',out['namePrefix']):raise ValueError('命名前缀不能包含路径或文件名保留字符')
    return out

def filename(video,opts,index=0):
    stem=Path(video['path']).stem
    if opts['naming']=='episode':stem=(opts['namePrefix']+'_' if opts['namePrefix'] else '')+f'第{opts["startNumber"]+index:0{opts["digits"]}d}集'
    stem=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',stem).strip(' .')[:100] or '未命名'
    if stem.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}:stem='_'+stem
    return f'{stem}_{opts["tracks"]}轨.png'

def output_directory(video,opts):
    source=Path(video['path']).resolve()
    if not opts['output']:return source.parent/'工程图输出'
    root=Path(opts['output']).resolve()
    name=re.sub(r'[<>:"/\\|?*]','_',source.parent.name).strip(' .')[:60] or '素材'
    suffix=hashlib.sha256(str(source.parent).casefold().encode()).hexdigest()[:6]
    return root/(name+'_'+suffix)

def cancelled(event):
    if event.is_set():raise InterruptedError('分轨工程图任务已停止，已完成图片保留')

def source_hash(path,event,notify=lambda *a:None):
    h=hashlib.sha256();done=0;total=path.stat().st_size
    with path.open('rb') as stream:
        while block:=stream.read(2*1024*1024):
            cancelled(event);h.update(block);done+=len(block);notify('hash',done,total)
    return h.hexdigest()

def _write_json(path,value):
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:temp.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':')),'utf-8');temp.replace(path)
    finally:temp.unlink(missing_ok=True)

def _remove_work(path,root):
    p=path.resolve();r=root.resolve()
    if p==r or not p.is_relative_to(r):raise ValueError('缓存临时目录超出范围')
    if p.exists():shutil.rmtree(p)

def _invoke(ffmpeg,args,run,notify=None,timeout=300):
    command=[str(ffmpeg),'-hide_banner','-loglevel','error','-nostdin','-nostats','-y']
    if notify:command+=['-stats_period','0.25','-progress','pipe:1']
    return run(command+list(map(str,args)),observe=notify,timeout=timeout)

def _decode_device(source,opts,ffmpeg,run,event,work):
    if opts['device']=='cpu':return [],{'backend':'cpu','label':'CPU 解码与分析','fallback':False}
    choices=[]
    cuda=['-hwaccel','cuda']
    if opts['gpuIndex']>=0:cuda+=['-hwaccel_device',str(opts['gpuIndex'])]
    choices.append(('cuda','NVIDIA CUDA 解码 · CPU 分析',cuda))
    if opts['gpuIndex']<0:choices.append(('d3d11va','D3D11VA 硬件解码 · CPU 分析',['-hwaccel','d3d11va']))
    for backend,label,flags in choices:
        cancelled(event)
        probe=work/('probe-'+backend);probe.mkdir()
        try:
            _invoke(ffmpeg,[*flags,'-i',source,'-map','0:v:0','-an','-frames:v','3','-vf','scale=160:90',probe/'%02d.jpg'],run,timeout=6)
            frames=list(probe.glob('*.jpg'))
            if not frames:raise RuntimeError('硬件解码未输出有效帧')
            for frame in frames:
                with Image.open(frame) as image:image.verify()
            return flags,{'backend':backend,'label':label,'fallback':False}
        except InterruptedError:raise
        except (RuntimeError,OSError,ValueError):continue
    return [],{'backend':'cpu','label':'CPU 解码与分析','fallback':True,'reason':'当前素材的硬件解码测试未通过，已自动使用 CPU'}

def _waveform(path,bins=1500):
    with wave.open(str(path),'rb') as reader:
        count=reader.getnframes();length=min(count,bins)
        if not length:return []
        result=[];previous=0
        for i in range(length):
            end=round((i+1)*count/length);values=array.array('h',reader.readframes(end-previous));previous=end
            if sys_byteorder()!='little':values.byteswap()
            result.append(round(math.sqrt(sum(v*v for v in values)/max(1,len(values)))/32768,5))
        return result

def sys_byteorder():
    import sys
    return sys.byteorder

def analyze(video,opts,cache_home,ffmpeg,run,event,notify=lambda *a:None):
    source=Path(video['path']).resolve();before=source.stat()
    duration=float(video['duration'])
    if not math.isfinite(duration) or not 0<duration<=21600:raise ValueError('仅支持6小时内的有效视频')
    digest=source_hash(source,event,notify)
    config={k:opts[k] for k in ('sampleInterval','threshold','minScene','maxSegment','device','gpuIndex')}
    key=hashlib.sha256(json.dumps({'version':VERSION,'source':digest,'analysis':config},sort_keys=True).encode()).hexdigest()
    root=Path(cache_home).resolve();root.mkdir(parents=True,exist_ok=True);folder=root/key
    with ANALYSIS_LOCK:
        cancelled(event)
        if opts['reuse'] and (folder/'analysis.json').is_file():
            try:
                data=json.loads((folder/'analysis.json').read_text('utf-8'))
                if data['sourceSHA256']!=digest or data['version']!=VERSION:raise ValueError('缓存不匹配')
                for frame in data['frames']:
                    p=(folder/frame['file']).resolve()
                    if not p.is_relative_to(folder) or hashlib.sha256(p.read_bytes()).hexdigest()!=frame['sha256']:raise ValueError('抽帧缓存不完整')
                after=source.stat()
                if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('分析时源视频发生变化')
                notify('cache',1,1)
                return data,folder,True
            except (OSError,ValueError,KeyError,TypeError):pass
        work=root/('work-'+uuid.uuid4().hex);work.mkdir()
        try:
            if shutil.disk_usage(work).free<64*1024**2:raise ValueError('缓存磁盘可用空间不足64MB')
            notify('device',None,None)
            flags,device=_decode_device(source,opts,ffmpeg,run,event,work);notify('backend',device,None)
            step=max(opts['sampleInterval'],duration/360)
            frame_times={}
            def progress(line):
                cancelled(event)
                frame=re.search(r'\bn:\s*(\d+)\s+pts:\s*-?\d+\s+pts_time:([\d.eE+-]+)',line)
                if frame:frame_times[int(frame[1])]=float(frame[2])
                m=re.fullmatch(r'out_time_us=(\d+)',line)
                if m:notify('decode',min(duration,int(m[1])/1e6),duration)
            frame_args=['-loglevel','info','-i',source,'-map','0:v:0','-an','-vf',f"select='isnan(prev_selected_t)+gte(t-prev_selected_t,{step:.8f})',scale=320:320:force_original_aspect_ratio=decrease,showinfo",'-fps_mode','vfr','-frames:v','362','-q:v','5',work/'frame_%04d.jpg']
            notify('decode',0,duration)
            try:_invoke(ffmpeg,[*flags,*frame_args],run,progress,timeout=max(60,min(1800,duration*2)))
            except InterruptedError:raise
            except RuntimeError:
                if not flags:raise
                for p in work.glob('frame_*.jpg'):p.unlink()
                device={'backend':'cpu','label':'CPU 解码与分析','fallback':True,'reason':'硬件解码在运行中失败，已使用 CPU 重新分析本集'}
                frame_times.clear();notify('backend',device,None)
                _invoke(ffmpeg,frame_args,run,progress,timeout=max(60,min(1800,duration*2)))
            paths=sorted(work.glob('frame_*.jpg'))
            if not paths:
                _invoke(ffmpeg,['-i',source,'-map','0:v:0','-frames:v','1',work/'frame_0001.jpg'],run,timeout=30)
                paths=sorted(work.glob('frame_*.jpg'))
            frames=[];cuts=[0.];previous=None
            for i,path in enumerate(paths):
                cancelled(event)
                with Image.open(path) as image:
                    small=image.convert('RGB').resize((96,54));score=0 if previous is None else sum(ImageStat.Stat(ImageChops.difference(small,previous)).mean)/3
                    previous=small
                timestamp=min(duration,max(0,frame_times.get(i,i*step)))
                frames.append({'file':path.name,'time':round(timestamp,6),'score':round(score,3),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
                if score>=opts['threshold'] and timestamp-cuts[-1]>=opts['minScene'] and duration-timestamp>=.1:cuts.append(timestamp)
                notify('analyze',i+1,len(paths))
            cuts.append(duration);segments=[]
            for start,end in zip(cuts,cuts[1:]):
                count=max(1,math.ceil((end-start)/opts['maxSegment']))
                for i in range(count):
                    a=start+(end-start)*i/count;b=start+(end-start)*(i+1)/count
                    if b-a<=.00001:continue
                    middle=(a+b)/2;frame=min(range(len(frames)),key=lambda j:abs(frames[j]['time']-middle))
                    segments.append({'start':round(a,6),'end':round(b,6),'frame':frame,'reason':'scene' if count==1 else 'duration_split'})
            peaks=[]
            if video.get('audio'):
                audio=work/'original-audio.wav'
                _invoke(ffmpeg,['-i',source,'-map','0:a:0','-vn','-ac','1','-ar','1000','-c:a','pcm_s16le',audio],run,timeout=max(60,min(900,duration)))
                peaks=_waveform(audio);audio.unlink()
            after=source.stat()
            if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('分析时源视频发生变化，请重新生成')
            data={'version':VERSION,'key':key,'sourceSHA256':digest,'sourceBytes':before.st_size,'sourceMtimeNs':before.st_mtime_ns,
                  'duration':duration,'width':video['width'],'height':video['height'],'audio':bool(video.get('audio')),
                  'sampleInterval':step,'frames':frames,'segments':segments,'waveform':peaks,'device':device,'analysisOptions':config,'analyzedAt':time.time()}
            for p in work.glob('probe-*'):_remove_work(p,root)
            _write_json(work/'analysis.json',data)
            cancelled(event)
            if folder.exists():_remove_work(folder,root)
            work.replace(folder)
            return data,folder,False
        finally:
            if work.exists():_remove_work(work,root)

@lru_cache(maxsize=32)
def font(size,bold=False):
    path=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/('msyhbd.ttc' if bold else 'msyh.ttc')
    try:return ImageFont.truetype(str(path),size)
    except OSError:return ImageFont.truetype('DejaVuSans.ttf',size)

def timecode(value):
    value=max(0,float(value));return f'{int(value)//60:02d}:{int(value)%60:02d}.{int(value*10)%10}'

def render(data,folder,source_name,opts,event):
    scale=opts['width']/2560;w=opts['width'];tracks=opts['tracks'];h=round((640+tracks*94+100)*scale)
    canvas=Image.new('RGB',(w,h),'#171B28');d=ImageDraw.Draw(canvas)
    def box(rect,fill,outline=None,radius=0):
        rect=tuple(round(v*scale) for v in rect)
        if radius:d.rounded_rectangle(rect,radius=round(radius*scale),fill=fill,outline=outline)
        else:d.rectangle(rect,fill=fill,outline=outline)
    def text(x,y,value,size=24,fill='#D9DFEC',bold=False,max_width=None):
        value=str(value);f=font(max(10,round(size*scale)),bold)
        if max_width and d.textlength(value,font=f)>max_width*scale:
            while value and d.textlength(value+'…',font=f)>max_width*scale:value=value[:-1]
            value+='…'
        d.text((round(x*scale),round(y*scale)),value,font=f,fill=fill)
    box((0,0,2560,98),'#23283B');box((32,26,42,72),'#A68DF5',radius=4)
    text(64,24,'漫剧工坊  /  分轨工程图',32,bold=True);text(1910,35,f'{tracks} 轨布局     {timecode(data["duration"])}',25)
    text(48,120,source_name,32,bold=True,max_width=1850)
    text(48,174,f'{data["width"]} × {data["height"]}    ·    {len(data["segments"])} 个视频片段    ·    采样间隔 {data["sampleInterval"]:.2f} 秒',22,fill='#ABB5CC')
    representatives=[0,len(data['frames'])//2,len(data['frames'])-1]
    for i,index in enumerate(representatives):
        cancelled(event);frame=data['frames'][index];x=48+i*824
        box((x,226,x+792,556),'#0C0F17',radius=10)
        with Image.open(folder/frame['file']) as image:
            thumb=ImageOps.contain(image.convert('RGB'),(round(750*scale),round(288*scale)))
        canvas.paste(thumb,(round((x+396)*scale)-thumb.width//2,round(242*scale)+(round(288*scale)-thumb.height)//2))
        text(x+20,562,'源帧  '+timecode(frame['time']),21,fill='#ABB5CC')
    left=190;right=2512;usable=right-left;top=640;row_h=94;dur=data['duration']
    box((48,608,2512,636),'#22283A')
    for i in range(9):
        at=dur*i/8;x=left+usable*i/8
        text(x-24,604,timecode(at),17,fill='#99A7C0')
        d.line((round(x*scale),round(top*scale),round(x*scale),round((top+tracks*row_h)*scale)),fill='#30384C',width=1)
    has_audio=bool(data['audio'] and data['waveform']);video_lanes=tracks-(1 if has_audio else 0)
    colors=('#7C6AC6','#3C789B','#527A72','#947048','#7D5986','#596F9F','#4E8086','#98676C','#717B52')
    for lane in range(tracks):
        y=top+lane*row_h;box((48,y,172,y+row_h-8),'#252C40',radius=7)
        text(68,y+17,('A01' if has_audio and lane==tracks-1 else f'V{lane+1:02d}'),23,bold=True)
        text(68,y+50,'原声' if has_audio and lane==tracks-1 else '视频分段',17,fill='#A6B2CD')
        box((left,y,right,y+row_h-8),'#202637')
    for i,segment in enumerate(data['segments']):
        cancelled(event);lane=i%video_lanes;y=top+lane*row_h;x=left+usable*segment['start']/dur;end=left+usable*segment['end']/dur
        end=max(x+1,end);box((x,y+3,end,y+row_h-11),colors[lane%len(colors)],radius=3)
        if end-x>=42:
            frame=data['frames'][segment['frame']]
            with Image.open(folder/frame['file']) as image:thumb=ImageOps.fit(image.convert('RGB'),(max(1,round(min(100,end-x-4)*scale)),round(52*scale)))
            canvas.paste(thumb,(round((x+2)*scale),round((y+6)*scale)))
        if end-x>114:text(x+7,y+62,timecode(segment['start']),15,fill='#FFFFFF')
    if has_audio:
        y=top+(tracks-1)*row_h;box((left,y+3,right,y+row_h-11),'#25483F',radius=4)
        values=data['waveform'];peak=max(max(values),.01)
        for i,v in enumerate(values):
            x=(left+usable*i/max(1,len(values)-1))*scale;amplitude=min(1,v/peak)*29*scale;center=(y+42)*scale
            d.line((round(x),round(center-amplitude),round(x),round(center+amplitude)),fill='#70C9AB',width=max(1,round(scale)))
        text(left+12,y+61,'源视频原声 · 实际波形',15,fill='#BDE5D7')
    y=top+tracks*row_h+20
    text(48,y,'真实视频抽帧与时间分段视图  ·  原素材保持不变',20,fill='#ABB5CC')
    text(48,y+35,'SHA256  '+data['sourceSHA256'],17,fill='#8493B0')
    return canvas

def generate(video,opts,cache_home,ffmpeg,run,event,index=0,notify=lambda *a:None):
    opts=options(opts);started=time.monotonic()
    data,folder,hit=analyze(video,opts,cache_home,ffmpeg,run,event,notify)
    directory=output_directory(video,opts);directory.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(directory).free<64*1024**2:raise ValueError('工程图输出磁盘可用空间不足64MB')
    planned=directory/filename(video,opts,index);target=planned;count=1
    while target.exists() or target.with_suffix('.json').exists():
        count+=1;target=planned.with_name(planned.stem+f'_{count}'+planned.suffix)
        if count>10000:raise ValueError('同名工程图过多，请更换输出目录')
    notify('render',0,1);image=render(data,folder,Path(video['path']).name,opts,event)
    temp=target.with_name('.'+uuid.uuid4().hex+'.png.part');json_path=target.with_suffix('.json')
    try:
        cancelled(event);image.save(temp,format='PNG',compress_level=1 if opts['fastPng'] else 6,optimize=False)
        cancelled(event)
        with Image.open(temp) as check:
            check.verify()
        image_hash=hashlib.sha256(temp.read_bytes()).hexdigest()
        manifest={'format':1,'kind':'track_sheet','sourceFile':Path(video['path']).name,'sourceSHA256':data['sourceSHA256'],
                  'duration':data['duration'],'tracks':opts['tracks'],'audio':data['audio'],'segments':data['segments'],
                  'samples':[{'time':f['time'],'sha256':f['sha256']} for f in data['frames']],
                  'imageFile':target.name,'imageSHA256':image_hash,'width':image.width,'height':image.height,
                  'options':{k:v for k,v in opts.items() if k!='output'},'device':data['device'],'cacheHit':hit}
        _write_json(json_path,manifest);temp.replace(target)
        notify('render',1,1)
        return {'path':str(target),'manifest':str(json_path),'sourceFile':Path(video['path']).name,'tracks':opts['tracks'],
                'duration':data['duration'],'segments':len(data['segments']),'samples':len(data['frames']),'cacheHit':hit,
                'device':data['device'],'seconds':round(time.monotonic()-started,3),'imageSHA256':image_hash,
                'manifestSHA256':hashlib.sha256(json_path.read_bytes()).hexdigest(),'sourceSHA256':data['sourceSHA256']}
    except Exception:
        if not target.exists():json_path.unlink(missing_ok=True)
        raise
    finally:image.close();temp.unlink(missing_ok=True)
