"""Real-model tail boundary, all-preserved and worker reuse regression."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT))
import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFont
import lama_local
import vsr_pool


def main():
    out=Path(tempfile.mkdtemp(prefix='subtitle-tail-workers-',dir=ROOT/'tmp'))
    ffmpeg=next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe'))
    install=json.loads((ROOT/'engines/vsr-install.json').read_text('utf-8'))
    source=out/'boundary-source.mp4'
    encoder=subprocess.Popen([str(ffmpeg),'-hide_banner','-loglevel','error','-nostdin','-y',
        '-f','rawvideo','-pix_fmt','rgb24','-s','640x368','-r','24','-i','pipe:0',
        '-an','-c:v','libx264','-preset','fast','-crf','18','-threads','2',str(source)],stdin=subprocess.PIPE)
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',30)
    yy,xx=np.indices((368,640))
    base=np.stack([(xx//6+40)%170,(yy//3+30)%170,np.full_like(xx,85)],axis=-1).astype(np.uint8)
    for index in range(60):
        frame=Image.fromarray(base)
        draw=ImageDraw.Draw(frame)
        draw.text((150,253),'字幕保留边界测试',font=font,fill='white',stroke_width=2,stroke_fill='black')
        draw.ellipse((index*7%600,30,index*7%600+25,55),fill='red')
        encoder.stdin.write(frame.tobytes())
    encoder.stdin.close()
    if encoder.wait(timeout=60):raise RuntimeError('Fixture encoding failed')
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    report={'ok':False,'base':str(out),'sourceSHA256':digest,'checks':[],'runs':[],'realModels':True}
    def check(name,value):
        if not value:raise AssertionError(name)
        report['checks'].append(name)
        print('PASS '+name,flush=True)
    def frames(path):
        cap=cv2.VideoCapture(str(path));result=[]
        while True:
            ok,frame=cap.read()
            if not ok:break
            result.append(frame)
        cap.release()
        return result
    original=frames(source)
    try:
        for mode,pool in [('lama-box',lama_local.POOL),('sttn-auto',vsr_pool.POOL)]:
            previous_pid=None
            for keep,cutoff in [(0,60),(.5,48),(10,0)]:
                target=out/f'{mode}-{keep}.mp4'
                request={'input':str(source),'output':str(target),'mode':mode,'regions':[[248,301,100,540]],
                    'duration':2.5,'device':'auto','ffmpeg':str(ffmpeg),'preserveTailSeconds':keep}
                started=time.monotonic()
                stats=pool.run(install['python'],install['root'],request,threading.Event(),
                    lambda line:None)
                output=frames(target)
                check(mode+f'_{keep}_all_frames_retained',len(output)==len(original)==60)
                diffs=[float(np.abs(a[248:301,100:540].astype(float)-b[248:301,100:540].astype(float)).mean())
                    for a,b in zip(original,output)]
                record={'mode':mode,'keep':keep,'cutoff':cutoff,'worker':stats,'roiMeanDifferenceByFrame':diffs,
                    'seconds':round(time.monotonic()-started,3),'output':str(target)}
                report['runs'].append(record)
                check(mode+f'_{keep}_statistics_match_boundary',stats['processedFrames']==cutoff and stats['preservedTailFrames']==60-cutoff)
                if previous_pid is not None:check(mode+f'_{keep}_same_worker_reused',stats['pid']==previous_pid and stats['reusedProcess'])
                previous_pid=stats['pid']
                if keep:
                    check(mode+f'_{keep}_every_preserved_frame_retains_pixels',max(diffs[cutoff:])<3)
                    if cutoff:check(mode+'_frame_before_boundary_is_processed',diffs[cutoff-1]>max(diffs[cutoff:])*2 and diffs[cutoff-1]>3)
                else:check(mode+'_default_processes_the_last_frame',diffs[-1]>3)
                subprocess.run([str(ffmpeg),'-v','error','-xerror','-err_detect','explode','-i',str(target),'-f','null','NUL'],
                    check=True,capture_output=True,timeout=60)
                (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
            pool.close()
        check('original_source_unchanged',hashlib.sha256(source.read_bytes()).hexdigest()==digest)
        report['ok']=True
    finally:
        lama_local.POOL.close();vsr_pool.POOL.close()
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
        (ROOT/'tmp/subtitle-tail-workers-latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps({'ok':report['ok'],'base':str(out),'checks':len(report['checks'])}),flush=True)


if __name__=='__main__':main()
