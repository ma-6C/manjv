"""Inspect real collected captions with the installed offline STTN worker."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--seed',type=Path,default=ROOT/'tmp/final-hongguo-manager-e2e-latest.json')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--full',action='store_true')
    parser.add_argument('--mode',choices=['sttn-auto','lama-box'],default='sttn-auto')
    parser.add_argument('--tail',action='store_true')
    parser.add_argument('--indices',nargs='+',type=int,default=[1,2,3])
    parser.add_argument('--preserve-tail',type=float,default=0)
    args=parser.parse_args()
    out=args.output.resolve()
    if not out.is_relative_to((ROOT/'tmp').resolve()):raise ValueError('Use isolated tmp output')
    out.mkdir(parents=True,exist_ok=True)
    seed=json.loads(args.seed.read_text('utf-8'))
    ffmpeg=next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe'))
    install=json.loads((ROOT/'engines/vsr-install.json').read_text('utf-8'))
    os.environ['MANJU_DATA']=str(out/'isolated-data')
    os.environ['PYTHONDONTWRITEBYTECODE']='1'
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TRANSFORMERS_OFFLINE']='1'
    sys.dont_write_bytecode=True
    sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
    import server
    import vsr_pool
    import lama_local
    pool=lama_local.POOL if args.mode=='lama-box' else vsr_pool.POOL
    report={'ok':False,'full':args.full,'collectionCoreSHA256':seed['dllSha256'],
        'collectionReport':seed.get('report'),'networkModelsDownloaded':False,
        'interface':'production vsr_pool.Pool.run','mode':args.mode,
        'automaticDetection':False,'tail':args.tail,'visualAcceptance':'pending human inspection',
        'clips':[]}
    def sha(path):
        with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
    def ff(extra,timeout=180):
        subprocess.run([str(ffmpeg),'-hide_banner','-loglevel','error','-nostdin','-y',*map(str,extra)],
            check=True,capture_output=True,timeout=timeout,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        for i,video in enumerate(seed['videos'],1):
            if i not in args.indices:continue
            source=Path(video['path'])
            original_hash=sha(source)
            if original_hash!=video['sha256']:raise ValueError('Collected source changed')
            srcmeta=server.probe(source)
            region={'x':.12,'y':.692 if i<3 else .62,'w':.76,'h':.04 if i<3 else .06}
            start=12 if i<3 else 32
            if args.tail:start=max(0,srcmeta['duration']-6)
            seconds=srcmeta['duration'] if args.full else 6
            inp=source if args.full else out/f'clip-{i}.mp4'
            if not args.full:
                ff(['-ss',start,'-i',source,'-t',seconds,'-map','0:v:0','-map','0:a:0?',
                    '-c:v','libx264','-crf','18','-preset','fast','-threads','2','-c:a','aac',inp])
            target=out/f'{args.mode}-{i}.mp4'
            w,h=srcmeta['width'],srcmeta['height']
            coords=[[int(region['y']*h),int((region['y']+region['h'])*h),
                int(region['x']*w),int((region['x']+region['w'])*w)]]
            entry={'source':str(source),'sourceSHA256':original_hash,'input':str(inp),'output':str(target),
                'sourceStart':0 if args.full else start,'seconds':seconds,'region':region,'pixelRegions':coords}
            report['clips'].append(entry)
            started=time.monotonic()
            logfile=out/f'engine-{i}.log'
            last_print=0
            def observe(line):
                nonlocal last_print
                with logfile.open('a',encoding='utf-8') as stream:stream.write(str(line)+'\n')
                if 'inference device' in str(line) or time.monotonic()-last_print>20:
                    print(str(line).strip()[-240:],flush=True);last_print=time.monotonic()
            print(json.dumps({'processing':i,'seconds':seconds,'regions':coords}),flush=True)
            entry['worker']=pool.run(install['python'],install['root'],
                {'input':str(inp),'output':str(target),'mode':args.mode,'regions':coords,
                 'duration':seconds,'device':'auto','ffmpeg':str(ffmpeg),
                 'preserveTailSeconds':args.preserve_tail},threading.Event(),observe)
            entry['secondsElapsed']=round(time.monotonic()-started,3)
            entry['meta']=server.probe(target)
            if srcmeta['audio'] and not entry['meta']['audio']:
                restored=out/f'audio-{i}.mp4'
                ff(['-i',target,'-i',inp,'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k',restored])
                restored.replace(target)
                entry['meta']=server.probe(target)
            if abs(entry['meta']['duration']-seconds)>.3:raise ValueError('Output duration changed')
            if srcmeta['audio'] and not entry['meta']['audio']:raise ValueError('Output missing audio')
            ff(['-xerror','-err_detect','explode','-i',target,'-map','0:v:0','-map','0:a:0?',
                '-f','null','NUL'],timeout=600)
            if sha(source)!=original_hash:raise ValueError('Source media changed')
            entry['outputSHA256']=sha(target)
            entry['fullDecodePassed']=True
            frame_times=[.5,2.5,4.5,5.5] if not args.full else [min(12,seconds/4),min(17,seconds/2),seconds-2]
            entry['frames']=[]
            for number,second in enumerate(frame_times,1):
                paths={}
                for label,path in [('before',inp),('after',target)]:
                    frame=out/f'{label}-{i}-{number}.png'
                    ff(['-ss',second,'-i',path,'-frames:v','1',frame])
                    paths[label]=str(frame)
                entry['frames'].append({'second':second,**paths})
            (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
            print(json.dumps({'done':i,'secondsElapsed':entry['secondsElapsed'],'device':entry['worker']['device']}),flush=True)
        report['ok']=True
    finally:
        pool.close()
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print(str(out/'report.json'),flush=True)


if __name__=='__main__':main()
