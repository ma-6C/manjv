"""Single-pass highlight composition: source, optional tail, freeze and freeze-only music."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import random,threading,math

AUDIO={'.mp3','.wav','.m4a','.aac','.flac','.ogg'}
VIDEO={'.mp4','.mov','.mkv','.avi','.m4v','.webm','.ts'}

def validate(cfg,require_files=False):
    for key in ('highlightMusic','highlightTailDirectory','highlightTailChoice'):
        value=cfg[key]
        if not isinstance(value,str) or len(value)>2000 or any(ord(c)<32 for c in value):raise ValueError('高光素材路径无效')
    for key,ext in [('highlightMusic',AUDIO)]:
        if cfg[key] and (not Path(cfg[key]).is_absolute() or Path(cfg[key]).suffix.lower() not in ext):raise ValueError('请选择有效的本地音乐文件')
        if require_files and cfg[key] and not Path(cfg[key]).is_file():raise ValueError('定格配乐文件不存在')
    if cfg['highlightTailDirectory'] and not Path(cfg['highlightTailDirectory']).is_absolute():raise ValueError('结尾模板请选择绝对目录')
    if cfg['highlightTailChoice']!='random' and (Path(cfg['highlightTailChoice']).name!=cfg['highlightTailChoice'] or Path(cfg['highlightTailChoice']).suffix.lower() not in VIDEO):raise ValueError('结尾模板选择无效')
    if require_files and cfg['highlightTailEnabled'] and not templates(cfg):raise ValueError('结尾模板目录没有可用的视频')
    if require_files and cfg['highlightTailEnabled'] and cfg['highlightTailChoice']!='random' and cfg['highlightTailChoice'] not in [p.name for p in templates(cfg)]:raise ValueError('所选结尾模板已被移动或删除')

def templates(cfg):
    folder=Path(cfg['highlightTailDirectory']) if cfg['highlightTailDirectory'] else None
    return sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO),key=lambda p:p.name)[:500] if folder and folder.is_dir() else []

def render(api,p,cfg,jid):
    validate(cfg,True);job=api.JOBS[jid];out=api.project_dir(p,cfg)/'高光包装'/jid;out.mkdir(parents=True,exist_ok=True)
    cfg=dict(cfg)
    if cfg['highlightLowResource']:cfg['gpu']=False
    parallel=1 if cfg['highlightLowResource'] else cfg['highlightParallel']
    videos=p['videos'];tasks=[(i,n,v) for i,v in enumerate(videos) for n in range(cfg['highlightCount'])]
    done=0;lock=threading.Lock();outputs={};plans=job.setdefault('highlightPlan',{})
    # Persist the random choices before encoding so pause/resume retains the same composition.
    for i,n,v in tasks:
        key=f'{p["id"]}:highlight:{i}:{n}'
        if key not in plans:
            ratio=random.uniform(cfg['highlightMin'],cfg['highlightMax']) if cfg['highlightRandom'] else cfg['highlightFixed']
            choices=templates(cfg) if cfg['highlightTailEnabled'] else []
            tail=random.choice(choices) if choices and cfg['highlightTailChoice']=='random' else next((x for x in choices if x.name==cfg['highlightTailChoice']),None)
            plans[key]={'ratio':ratio,'tail':str(tail) if tail else '', 'music':cfg['highlightMusic']}
        plan=plans[key]
        for field in ('tail','music'):
            if plan[field]:
                st=Path(plan[field]).stat();current={'bytes':st.st_size,'mtime':st.st_mtime_ns}
                if field+'Stat' in plan and plan[field+'Stat']!=current:raise ValueError('高光配乐或模板发生变化，请创建新任务')
                plan[field+'Stat']=current
    api.persist_jobs();api.encoder(cfg,jid) # Establish one tested encoder before parallel workers.
    def one(item):
        nonlocal done
        i,n,v=item;key=f'{p["id"]}:highlight:{i}:{n}';plan=plans[key]
        if job['cancel'].is_set():raise InterruptedError('高光任务已停止')
        old=api.cached(jid,key)
        if old:target=old[0]
        else:
            stem=Path(v['path']).stem[:75];target=out/f'{stem}_{i+1:03d}_{n+1:02d}.mp4'
            args=['-i',v['path']];filters=[];idx=1
            def audio(video,label,speed=1):
                nonlocal idx
                if video.get('audio'):
                    filters.append(f'[{label}:a:0]aresample=48000,aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS'+(f',atempo={speed}' if speed!=1 else '')+f',atrim=duration={video["duration"]/speed},apad=whole_dur={video["duration"]/speed}[a{label}]')
                else:
                    args.extend(['-f','lavfi','-i','anullsrc=channel_layout=stereo:sample_rate=48000']);filters.append(f'[{idx}:a]atrim=duration={video["duration"]/speed},asetpts=PTS-STARTPTS[a{label}]');idx+=1
            base=v['duration']/cfg['speed'];filters.append(f'[0:v]{api.filters(cfg,v,out)},fps=30,format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS[v0]');audio(v,0,cfg['speed'])
            tail=plan['tail']
            if tail:
                t=api.probe(tail);ti=idx;idx+=1;args.extend(['-i',tail]);w,h=cfg['width'],cfg['height']
                filters.append(f'[{ti}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS[vt]');audio(t,ti)
                filters.append(f'[v0][a0][vt][a{ti}]concat=n=2:v=1:a=1[basev][basea]');base+=t['duration'];vin='basev';ain='basea'
            else:vin='v0';ain='a0'
            freeze=base*plan['ratio'];duration=base+freeze
            # concat has an unspecified frame rate; normalize again before tpad,
            # otherwise a nonzero audio duration can hide missing freeze frames.
            filters.append(f'[{vin}]fps=30,tpad=stop_mode=clone:stop_duration={freeze}[freeze]')
            ending=cfg['endingText'].strip()
            if ending and api.FONT:
                tf=out/f'ending-{i}-{n}.txt';tf.write_text(ending[:100],'utf-8')
                escaped=lambda path:str(path).replace('\\','/').replace(':','\\:').replace("'","\\'")
                filters.append(f"[freeze]drawtext=fontfile='{escaped(api.FONT)}':textfile='{escaped(tf)}':fontsize={max(16,int(cfg['width']/24))}:fontcolor=white:box=1:boxcolor=black@0.6:x=(w-tw)/2:y=h*0.75:enable='gte(t,{base})'[vout]")
            else:filters.append('[freeze]null[vout]')
            filters.append(f'[{ain}]apad,atrim=duration={duration}[original]')
            if plan['music'] and freeze>0:
                mi=idx;args.extend(['-stream_loop','-1','-i',plan['music']]);delay=round(base*1000)
                filters.append(f'[{mi}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=duration={freeze},asetpts=PTS-STARTPTS,adelay={delay}|{delay}[music]')
                filters.append('[original][music]amix=inputs=2:duration=first:normalize=0[aout]')
            else:filters.append('[original]anull[aout]')
            args+=['-filter_complex_threads','1','-filter_complex',';'.join(filters),'-map','[vout]','-map','[aout]',*api.encoder(cfg,jid),'-c:a','aac','-pix_fmt','yuv420p','-t',str(duration),'-threads','2',str(target)]
            api.encode_media(args,jid)
            actual=api.probe(target)
            if abs(actual['duration']-duration)>max(.3,duration*.005) or not actual['audio']:raise ValueError('高光成品时长或音轨校验失败')
            endcheck=out/f'.endcheck-{i}-{n}.jpg'
            try:
                api.ff(['-ss',str(max(0,duration-.2)),'-i',str(target),'-frames:v','1','-vf','scale=32:32',str(endcheck)],jid)
                if not endcheck.is_file() or endcheck.stat().st_size<100:raise ValueError('高光成品末段没有有效画面，已保留文件供排查')
            finally:endcheck.unlink(missing_ok=True)
            with api.LOCK:api.register(p,target,'高光视频',jid);api.checkpoint(jid,key,[target])
        with lock:
            outputs[(i,n)]=target;done+=1;api.stage(jid,f'高光包装：完成 {done}/{len(tasks)} 份',10+done/len(tasks)*80)
        return target
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        futures=[pool.submit(one,t) for t in tasks]
        try:
            for f in as_completed(futures):f.result()
        except BaseException:
            for f in futures:f.cancel()
            raise
    return [outputs[key] for key in sorted(outputs)]
