"""Offline speech/stem jobs, isolated from the desktop application's Python.

Models are local inputs. A failed GPU process is discarded before CPU retry;
neither an empty stem nor a subtitle placeholder is accepted as an AI result.
"""
from pathlib import Path
import json
import math
import wave


WORKER = r'''
import json, os, sys, traceback, wave, importlib.metadata, inspect
from pathlib import Path
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
request=Path(sys.argv[1]); output=Path(sys.argv[2])
cfg=json.loads(request.read_text('utf-8'))
def emit(value):
    output.write_text(json.dumps(value,ensure_ascii=False),'utf-8')
def separate():
    import numpy as np
    import torch
    from demucs.pretrained import get_model
    from demucs.apply import apply_model
    device=cfg['device']
    if device=='cuda' and not torch.cuda.is_available():device='cpu'
    if device=='cuda':
        (torch.ones(8,device=device)*2).sum().item()
    repo=(Path(cfg['modelRoot'])/'demucs').resolve()
    # Demucs 4 checkpoints include their model class. New torch versions
    # default to tensor-only loads; restrict its compatibility loader to the
    # explicitly selected local repository inside this disposable process.
    original_load=torch.load
    def load_local(file,*args,**kwargs):
        path=Path(file if isinstance(file,(str,Path)) else file.name).resolve()
        if not path.is_relative_to(repo):raise ValueError('分离模型引用超出指定的本地模型仓库')
        if 'weights_only' in inspect.signature(original_load).parameters:kwargs.setdefault('weights_only',False)
        return original_load(file,*args,**kwargs)
    torch.load=load_local
    try:model=get_model(cfg['modelName'],repo=repo)
    finally:torch.load=original_load
    model.eval().to(device)
    if model.samplerate!=44100 or model.audio_channels!=2:
        raise RuntimeError('分离模型必须使用 44100Hz 双声道输入')
    if 'vocals' not in model.sources:raise RuntimeError('模型没有 vocals 人声输出')
    voice=Path(cfg['voice']); background=Path(cfg['background'])
    with wave.open(cfg['audio'],'rb') as src, wave.open(str(voice),'wb') as vw, wave.open(str(background),'wb') as bw:
        if src.getsampwidth()!=2 or src.getnchannels()!=2 or src.getframerate()!=44100:
            raise RuntimeError('分离输入不是 44100Hz 双声道 PCM')
        for writer in (vw,bw):writer.setparams((2,2,44100,0,'NONE','not compressed'))
        total=src.getnframes(); block=20*44100; margin=44100; pos=0
        while pos<total:
            a=max(0,pos-margin);b=min(total,pos+block+margin)
            src.setpos(a)
            audio=np.frombuffer(src.readframes(b-a),dtype='<i2').astype('float32').reshape(-1,2).T/32768
            tensor=torch.from_numpy(audio.copy());ref=tensor.mean(0);mean=ref.mean();std=ref.std().clamp_min(1e-8)
            with torch.inference_mode():
                stems=apply_model(model,((tensor-mean)/std)[None],device=device,shifts=0,split=True,overlap=.25,progress=False)[0].cpu()*std+mean
            idx=model.sources.index('vocals');v=stems[idx]
            bg=stems[[i for i in range(len(model.sources)) if i!=idx]].sum(0)
            left=pos-a;right=left+min(block,total-pos)
            for writer,data in ((vw,v),(bw,bg)):
                pcm=(data[:,left:right].T.clamp(-1,1).numpy()*32767).astype('<i2')
                writer.writeframes(pcm.tobytes())
            pos+=min(block,total-pos)
            print('MANJU_AI_PROGRESS '+json.dumps({'phase':'separate','value':pos,'total':total}),flush=True)
    return {'ok':True,'device':device,'frames':total}
def transcribe():
    from faster_whisper import WhisperModel
    device=cfg['device']
    model=WhisperModel(str(Path(cfg['modelRoot'])/'faster-whisper'),device=device,
                       compute_type='float16' if device=='cuda' else 'int8',local_files_only=True)
    segments,info=model.transcribe(cfg['audio'],language=cfg['language'] or None,
        word_timestamps=True,vad_filter=True,condition_on_previous_text=False,beam_size=5)
    cues=[]
    for seg in segments:
        words=seg.words or [];group=[]
        def flush():
            if group:
                cues.append({'start':group[0].start,'end':group[-1].end,'text':''.join(w.word for w in group).strip()})
                group.clear()
        for word in words:
            if group and (len(''.join(w.word for w in group))+len(word.word)>cfg['captionLength'] or word.end-group[0].start>5):flush()
            group.append(word)
            if word.word.rstrip().endswith(('。','！','？','!','?')):flush()
        flush()
        if not words and seg.text.strip():cues.append({'start':seg.start,'end':seg.end,'text':seg.text.strip()})
        print('MANJU_AI_PROGRESS '+json.dumps({'phase':'asr','value':seg.end,'total':info.duration}),flush=True)
    return {'ok':True,'device':device,'language':info.language,'cues':cues}
try:
    result=separate() if cfg['action']=='separate' else transcribe()
    result['packages']={}
    for name in ('torch','torchaudio','demucs','faster-whisper','ctranslate2'):
        try:result['packages'][name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:pass
    emit(result)
except BaseException as exc:
    emit({'ok':False,'error':str(exc),'traceback':traceback.format_exc()[-12000:]})
    sys.exit(1)
'''


def runtime_options(opts,config):
    value=opts|{'aiPython':opts.get('aiPython') or config.get('vsrPython','')}
    if not value['aiModelRoot']:
        candidates=[]
        if config.get('vsrRoot'):candidates.append(Path(config['vsrRoot'])/'models/jianying')
        if value['aiPython']:
            runtime=Path(value['aiPython']).parent
            candidates.extend((runtime/'models/jianying',runtime.parent/'models/jianying'))
        value['aiModelRoot']=next((str(p.resolve()) for p in candidates if p.is_dir()),'')
    return value


def availability(opts):
    root=Path(opts['aiModelRoot']) if opts.get('aiModelRoot') else None
    python=Path(opts['aiPython']) if opts.get('aiPython') else None
    return {'runtimeConfigured':bool(python and python.is_file()),
            'asrModelPresent':bool(root and (root/'faster-whisper'/'model.bin').is_file()),
            'separationModelPresent':bool(root and (root/'demucs').is_dir() and any((root/'demucs').glob('*.th'))),
            'dependenciesVerified':False}


def worker(action,audio,resources,opts,run,event,notify):
    runtime=Path(opts['aiPython']) if opts['aiPython'] else None
    if not runtime or not runtime.is_file() or runtime.name.casefold() not in ('python.exe','pythonw.exe','python','python3'):
        raise ValueError('剪映 AI 引擎未配置可用 Python；请在本页选择独立 AI 引擎 Python')
    root=Path(opts['aiModelRoot']) if opts['aiModelRoot'] else None
    required=root/('demucs' if action=='separate' else 'faster-whisper') if root else None
    if not required or not required.is_dir():raise ValueError('缺少本地'+('人声分离' if action=='separate' else '语音识别')+'模型目录')
    work=resources/'AI任务';work.mkdir(exist_ok=True)
    request=work/(action+'-request.json');response=work/(action+'-response.json')
    errors=[]
    devices=['cuda','cpu'] if opts['aiDevice']=='auto' else ['cpu']
    for device in devices:
        if event.is_set():raise InterruptedError('剪映 AI 处理已停止')
        cfg={'action':action,'audio':str(audio),'device':device,'modelRoot':str(root),
             'modelName':opts['separationModel'],'language':opts['asrLanguage'],
             'captionLength':opts['captionLength'],'voice':str(resources/'人声.wav'),
             'background':str(resources/'背景声.wav')}
        request.write_text(json.dumps(cfg,ensure_ascii=False),'utf-8')
        response.unlink(missing_ok=True)
        def observe(line):
            if line.startswith('MANJU_AI_PROGRESS '):
                try:
                    value=json.loads(line[len('MANJU_AI_PROGRESS '):]);notify(value['phase'],value['value'],value['total'])
                except (ValueError,KeyError,TypeError):pass
        try:
            run([str(runtime),'-I','-u','-c',WORKER,str(request),str(response)],observe=observe,timeout=7200)
            value=json.loads(response.read_text('utf-8'))
            if value.get('ok') is not True:raise RuntimeError(value.get('error','AI 引擎没有返回处理结果'))
            value['fallbackErrors']=errors
            return value
        except InterruptedError:raise
        except Exception as exc:
            if event.is_set():raise InterruptedError('剪映 AI 处理已停止') from exc
            cause=str(exc)
            if response.is_file():
                try:cause=json.loads(response.read_text('utf-8')).get('error') or cause
                except (ValueError,OSError):pass
            errors.append(device+': '+cause[:2000])
            gpu_error=any(s in cause.lower() for s in ('cuda','cudnn','cublas','compute capability','out of memory','no kernel','float16'))
            if device!='cuda' or not gpu_error:break
            notify('cpu_fallback',0,1)
    raise RuntimeError('；'.join(errors))


def validate_stem(path,duration):
    with wave.open(str(path),'rb') as reader:
        actual=reader.getnframes()/reader.getframerate()
        if reader.getnchannels()!=2 or reader.getsampwidth()!=2 or abs(actual-duration/1e6)>.15:
            raise ValueError('人声分离输出时长或音频格式不完整：'+path.name)


def prepare(audio,resources,duration,opts,run,event,notify,need_captions):
    result={'stems':[],'cues':[],'warnings':[],'separation':'disabled','asr':'disabled','devices':{},'packages':{},'models':{}}
    def failure(stage,error):
        if opts['aiFailure']=='stop':raise RuntimeError(stage+'失败：'+str(error)) from error
        result['warnings'].append(stage+'失败：'+str(error)+'；'+('保留混合原声，未生成分离人声/背景声轨' if stage=='人声分离' else '未生成识别字幕轨'))
    if opts['audioMode']=='separate':
        notify('separate',0,1)
        try:
            value=worker('separate',audio,resources,opts,run,event,notify)
            paths=[resources/'人声.wav',resources/'背景声.wav']
            for path in paths:validate_stem(path,duration)
            result['stems']=paths;result['separation']='completed';result['devices']['separation']=value['device']
            result['packages'].update(value['packages']);result['models']['separation']=opts['separationModel']
            result['warnings'] += ['人声分离 GPU 失败后已使用 CPU：'+x for x in value['fallbackErrors']]
        except InterruptedError:raise
        except Exception as exc:result['separation']='failed';failure('人声分离',exc)
    if need_captions and opts['captionMode']=='auto':
        notify('asr',0,1)
        try:
            value=worker('asr',result['stems'][0] if result['stems'] else audio,resources,opts,run,event,notify)
            end=0
            for cue in value['cues']:
                a,b=float(cue['start']),float(cue['end'])
                if not math.isfinite(a+b) or a<0 or b<a or b*1e6>duration+150000:raise ValueError('识别结果时间码无效')
                a=max(end,round(a*1e6));b=min(duration,round(b*1e6))
                if cue['text'].strip() and b>a:result['cues'].append({'start':a,'end':b,'text':cue['text'].strip()});end=b
                if len(result['cues'])>10000:raise ValueError('识别字幕超过10000条')
            result['asr']='completed';result['devices']['asr']=value['device']
            result['packages'].update(value['packages']);result['models']['asr']=str(Path(opts['aiModelRoot'])/'faster-whisper')
            result['warnings'] += ['字幕识别 GPU 失败后已使用 CPU：'+x for x in value['fallbackErrors']]
        except InterruptedError:raise
        except Exception as exc:result['cues']=[];result['asr']='failed';failure('字幕识别',exc)
    return result
