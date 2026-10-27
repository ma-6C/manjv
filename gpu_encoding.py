"""Bounded NVIDIA/AMD/Intel hardware probes and classified CPU fallback."""
import copy,re,subprocess,threading,time,shutil,csv,io,json,os

CPU_ARGS=['-c:v','libx264','-preset','fast','-crf','21']
PROFILES=[('standard',['-c:v','h264_nvenc','-preset','p4','-cq','21','-forced-idr','1']),
          ('compatibility',['-c:v','h264_nvenc','-preset','default','-cq','21','-forced-idr','1'])]
BACKENDS=[
    {'id':'nvenc','name':'NVIDIA NVENC','codec':'h264_nvenc','profiles':PROFILES},
    {'id':'amf','name':'AMD AMF','codec':'h264_amf','profiles':[
        ('standard',['-c:v','h264_amf','-quality','balanced','-rc','cqp','-qp_i','21','-qp_p','21'])]},
    {'id':'qsv','name':'Intel Quick Sync','codec':'h264_qsv','profiles':[
        ('standard',['-c:v','h264_qsv','-preset','medium','-global_quality','21','-look_ahead','0','-forced_idr','1'])]},
]
HARDWARE_CODECS={b['codec'] for b in BACKENDS}
ENCODER_LABELS={'copy':'视频流复用／仅处理音轨','libx264':'CPU · libx264',**{b['codec']:'GPU · '+b['name'] for b in BACKENDS}}
LOCK=threading.RLock();CACHE={};ADAPTERS=None
FILTER_CACHE={};CHAIN_CACHE={}
QUALITY_LEVELS=('speed','balanced','quality')
QUALITY_LABELS={'speed':'速度优先','balanced':'平衡','quality':'画质优先'}
FILTER_NAMES=('cropdetect','scdet','blackdetect','freezedetect','ssim','psnr','libvmaf',
              'scale_cuda','colorspace_cuda','hwupload_cuda','hwdownload','signature')

def failure(error):
    text=str(error).lower()
    cases=[
        ('encoder_missing',('unknown encoder','encoder not found'),'当前媒体引擎未包含该硬件编码器'),
        ('driver_version',('driver does not support','minimum required nvidia driver','required nvenc api','unsupported nvenc api','driver version is insufficient'),'显卡驱动与当前媒体引擎所需的编码接口不兼容，请更新适用于本显卡的官方驱动'),
        ('driver_missing',('cannot load nvencodeapi','cannot load nvcuda','cannot load libnvidia-encode','cannot load libcuda','amfrt64','libamfrt','libmfx','libvpl'),'硬件编码驱动组件无法加载，请核对驱动安装'),
        ('no_device',('no capable devices','no nvenc capable','cuda_error_no_device','no cuda capable','cannot init cuda','cuinit(','no device available','device creation failed'),'当前运行环境未找到可用的硬件编码设备'),
        ('encoder_busy',('openencodesessionex failed','too many concurrent sessions','out of memory','encoder busy'),'硬件编码会话或显存资源不足，可关闭其他编码程序或降低并行数'),
        ('settings_unsupported',('initializeencoder failed','invalid param','unsupported device','unsupported resolution','does not support','unable to parse option value','undefined constant','error setting option preset','error while opening encoder','error initializing output stream','failed to open nvenc codec','error initializing an internal mfx session','unsupported (-3)','mfx_err_unsupported','mfx session','createcomponent','amf_not_supported','amf failed to initialise','amf failed to initialize','amf_create_component failed'),'显卡或驱动未接受当前硬件编码参数或画面尺寸'),
    ]
    for code,patterns,detail in cases:
        if any(p in text for p in patterns):return {'code':code,'detail':detail}
    return {'code':'probe_failed','detail':'硬件编码实际测试未通过，可重新检测或导出环境诊断'}

def startup_failure(error):
    text=str(error).lower()
    return any(x in text for x in ('nvenc','nvencodeapi','nvcuda','libcuda','cuinit(','h264_amf','h264_qsv','amfrt','mfx','libvpl')) and failure(error)['code']!='probe_failed'

def _run(args):
    result=subprocess.run(args,capture_output=True,timeout=8,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise RuntimeError(result.stderr.decode('utf-8','replace'))
    return result.stdout

def probe(ffmpeg,width=320,height=180,force=False,runner=None):
    run=runner or _run;key=(str(ffmpeg),int(width),int(height))
    with LOCK:
        previous=CACHE.get(key)
        if not force and previous and time.monotonic()-previous[0]<60:return copy.deepcopy(previous[1])
        outcomes=[];selected=None
        result={'available':False,'name':'硬件编码','code':'engine_missing','detail':'尚未找到 FFmpeg 媒体引擎','testedAt':time.time(),'width':int(width),'height':int(height),'attempts':0,'backends':outcomes}
        if ffmpeg:
            for backend in BACKENDS:
                outcome={'backend':backend['id'],'name':backend['name'],'available':False,'attempts':0}
                for profile,options in backend['profiles']:
                    outcome['attempts']+=1;result['attempts']+=1
                    pixel='nv12' if backend['id'] in ('amf','qsv') else 'yuv420p'
                    args=[str(ffmpeg),'-hide_banner','-loglevel','error','-nostdin','-f','lavfi','-i',f'color=s={int(width)}x{int(height)}:r=30',
                          '-frames:v','3','-an',*options,'-pix_fmt',pixel,'-bf','0','-progress','pipe:1','-f','null','-']
                    try:
                        raw=run(args);frames=re.findall(rb'^frame=(\d+)',raw,re.M)
                        if not frames or int(frames[-1])<3:raise RuntimeError('Hardware encoder returned no encoded frames')
                        outcome.update(available=True,code='ready',profile=profile,encoderArgs=options.copy(),detail='已通过当前尺寸的 H.264 硬件编码测试'+('（兼容参数）' if profile=='compatibility' else ''))
                        selected=outcome;break
                    except InterruptedError:raise
                    except (RuntimeError,OSError,subprocess.TimeoutExpired) as e:
                        outcome.update(failure(e))
                        if isinstance(e,subprocess.TimeoutExpired) or '超时' in str(e):outcome.update(code='probe_timeout',detail='硬件编码测试超时，将尝试其他编码器或 CPU')
                        if outcome['code'] in ('encoder_missing','driver_missing','driver_version','no_device','probe_timeout','encoder_busy'):break
                outcomes.append(outcome)
                if selected:break
            if selected:result.update({k:v for k,v in selected.items() if k!='attempts'})
            else:
                codes={x.get('code','probe_failed') for x in outcomes}
                result.update(code=next(iter(codes)) if len(codes)==1 else 'hardware_unavailable',
                    detail='硬件编码测试未通过，自动使用 CPU。'+'；'.join(x['name']+'：'+x.get('detail','未通过') for x in outcomes))
        CACHE[key]=(time.monotonic(),copy.deepcopy(result));return result


def adapters(force=False):
    global ADAPTERS
    with LOCK:
        if not force and ADAPTERS and time.monotonic()-ADAPTERS[0]<60:return copy.deepcopy(ADAPTERS[1])
        rows=[];exe=shutil.which('nvidia-smi')
        if exe:
            try:
                result=subprocess.run([exe,'--query-gpu=name,driver_version','--format=csv,noheader'],capture_output=True,timeout=3,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if result.returncode==0:
                    for row in csv.reader(io.StringIO(result.stdout.decode('utf-8','replace'))):
                        if len(row)==2:rows.append({'name':row[0].strip()[:120],'driverVersion':row[1].strip()[:40]})
            except (OSError,subprocess.TimeoutExpired):pass
        if os.name=='nt':
            try:
                command="[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);$items=@(Get-CimInstance Win32_VideoController -ErrorAction Stop | Select-Object Name,DriverVersion);ConvertTo-Json -InputObject $items -Compress"
                result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],capture_output=True,timeout=5,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if result.returncode==0:
                    for item in json.loads(result.stdout.decode('utf-8-sig','replace')):
                        name=str(item.get('Name',''))[:120]
                        if name and not any(r['name'].casefold()==name.casefold() for r in rows):rows.append({'name':name,'driverVersion':str(item.get('DriverVersion',''))[:40]})
            except (OSError,subprocess.TimeoutExpired,ValueError,TypeError):pass
        ADAPTERS=(time.monotonic(),rows);return copy.deepcopy(rows)

def _option(args,name,default=None):
    return args[args.index(name)+1] if name in args and args.index(name)+1<len(args) else default


def _put_option(args,name,value):
    if name in args:args[args.index(name)+1]=str(value)
    else:args.extend([name,str(value)])


def _quality(quality):
    if not isinstance(quality,str) or quality not in QUALITY_LEVELS:raise ValueError('编码画质档位无效')
    return quality


def quality_args(args,quality='balanced'):
    """Map a named quality to the selected encoder without changing its backend.

    Balanced is exactly the already-probed profile. A legacy NVENC profile keeps
    its accepted preset; its CQ can still be adjusted without introducing p1-p7.
    These are encoder-specific starting points, not equal-quality score claims.
    """
    quality=_quality(quality);result=list(args)
    if quality=='balanced':return result
    codec=_option(result,'-c:v');number=23 if quality=='speed' else 19
    if codec=='libx264':
        _put_option(result,'-preset','veryfast' if quality=='speed' else 'medium')
        _put_option(result,'-crf',number)
    elif codec=='h264_nvenc':
        if re.fullmatch(r'p[1-7]',str(_option(result,'-preset',''))):
            _put_option(result,'-preset','p2' if quality=='speed' else 'p6')
        _put_option(result,'-cq',number)
    elif codec=='h264_amf':
        _put_option(result,'-quality','speed' if quality=='speed' else 'quality')
        _put_option(result,'-qp_i',number);_put_option(result,'-qp_p',number)
    elif codec=='h264_qsv':
        _put_option(result,'-preset','veryfast' if quality=='speed' else 'slow')
        _put_option(result,'-global_quality',number)
    return result


def infer_quality(args):
    """Retain our named level when a hardware command falls back to the CPU."""
    for name in ('-cq','-global_quality','-qp_i','-crf'):
        value=_option(args,name)
        if value is not None:
            try:return {19:'quality',23:'speed'}.get(float(value),'balanced')
            except (ValueError,TypeError):return 'balanced'
    return 'balanced'


def cpu_arguments(args,quality=None):
    quality=_quality(quality) if quality is not None else infer_quality(args)
    result=[];i=0;gpu_options={'-preset','-crf','-cq','-rc','-gpu','-surfaces','-forced-idr','-forced_idr','-quality','-qp_i','-qp_p','-global_quality','-look_ahead'}
    while i<len(args):
        if args[i]=='-c:v':result+=['-c:v','libx264'];i+=2
        elif args[i] in gpu_options:i+=2
        elif args[i]=='-pix_fmt':result+=['-pix_fmt','yuv420p'];i+=2
        else:result.append(args[i]);i+=1
    cpu=quality_args(CPU_ARGS,quality)
    result[-1:-1]=cpu[2:];return result


def filter_capabilities(ffmpeg,force=False,runner=None):
    """Read the installed binary's filter list; no GPU execution is implied."""
    key=str(ffmpeg);run=runner or _run
    with LOCK:
        previous=FILTER_CACHE.get(key)
        if not force and previous and time.monotonic()-previous[0]<300:return copy.deepcopy(previous[1])
    result={'filters':{name:False for name in FILTER_NAMES},'listed':False,'runtimeTested':False,
            'testedAt':time.time(),'processing':'CPU画面处理；GPU开关选择编码器'}
    if ffmpeg:
        try:
            raw=run([str(ffmpeg),'-hide_banner','-nostdin','-filters'])
            text=raw.decode('utf-8','replace') if isinstance(raw,bytes) else str(raw)
            available=set(re.findall(r'^\s*[A-Z.]{3}\s+([A-Za-z0-9_]+)\s',text,re.M))
            result.update(listed=True,filters={name:name in available for name in FILTER_NAMES})
        except InterruptedError:raise
        except (OSError,RuntimeError,subprocess.TimeoutExpired) as error:
            result.update(code='filter_list_failed',detail='未能读取媒体引擎滤镜清单')
    else:result.update(code='engine_missing',detail='尚未找到 FFmpeg 媒体引擎')
    with LOCK:FILTER_CACHE[key]=(time.monotonic(),copy.deepcopy(result))
    return result


def probe_filter_chain(ffmpeg,width=320,height=180,force=False,runner=None):
    """Opt-in, three-frame CUDA upload/resize/download diagnostic.

    This tests only the named resize path. It does not enable the product's
    hardware decoder or move eq/crop/text filters onto the GPU.
    """
    if isinstance(width,bool) or isinstance(height,bool):raise ValueError('滤镜测试尺寸无效')
    try:w,h=int(width),int(height)
    except (ValueError,TypeError,OverflowError):raise ValueError('滤镜测试尺寸无效') from None
    if w!=float(width) or h!=float(height) or not 64<=w<=3840 or not 64<=h<=3840 or w%2 or h%2:raise ValueError('滤镜测试尺寸必须是64至3840之间的偶数')
    key=(str(ffmpeg),w,h);run=runner or _run
    with LOCK:
        previous=CHAIN_CACHE.get(key)
        if not force and previous and time.monotonic()-previous[0]<60:return copy.deepcopy(previous[1])
    source_w,source_h=(128,96) if (w,h)!=(128,96) else (64,64)
    operations=['format=nv12','hwupload_cuda',f'scale_cuda={w}:{h}','hwdownload','format=nv12']
    result={'available':False,'runtimeTested':False,'autoEnabled':False,'testedAt':time.time(),
            'width':w,'height':h,'inputWidth':source_w,'inputHeight':source_h,'frames':0,'operations':operations,
            'scope':'仅测试CUDA上传、缩放及下载，不代表整条制作流程使用GPU'}
    if ffmpeg:
        args=[str(ffmpeg),'-hide_banner','-loglevel','error','-nostdin','-f','lavfi','-i',f'color=s={source_w}x{source_h}:r=30',
              '-frames:v','3','-an','-vf',','.join(operations),'-progress','pipe:1','-f','null','-']
        try:
            raw=run(args);frames=re.findall(rb'^frame=(\d+)',raw,re.M)
            if not frames or int(frames[-1])<3:raise RuntimeError('GPU filter returned no filtered frames')
            result.update(available=True,runtimeTested=True,frames=int(frames[-1]),code='ready',detail='已通过3帧CUDA缩放测试；正式任务仍沿用兼容滤镜链')
        except InterruptedError:raise
        except (OSError,RuntimeError,subprocess.TimeoutExpired) as error:
            timed=isinstance(error,subprocess.TimeoutExpired)
            result.update(runtimeTested=True,code='probe_timeout' if timed else 'filter_chain_unavailable',
                          detail='CUDA滤镜测试超时，正式任务仍使用CPU画面处理' if timed else 'CUDA滤镜链未通过，正式任务仍使用CPU画面处理')
    else:result.update(code='engine_missing',detail='尚未找到 FFmpeg 媒体引擎')
    with LOCK:CHAIN_CACHE[key]=(time.monotonic(),copy.deepcopy(result))
    return result


def prepare_arguments(args):
    args=list(args)
    codec=args[args.index('-c:v')+1] if '-c:v' in args else ''
    if codec in ('h264_amf','h264_qsv') and '-pix_fmt' in args:args[args.index('-pix_fmt')+1]='nv12'
    return args
