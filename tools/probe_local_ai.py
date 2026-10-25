"""Offline feasibility probe using clean public OCR/ASR packages and local media.

This does not import, launch or modify any third-party application. Packages and
models must already be supplied locally. Production settings are never loaded.
"""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys,time,socket

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser()
    for arg in ('video','vendor','model','output'):parser.add_argument('--'+arg,type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(args.vendor.resolve()))
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',OMP_NUM_THREADS='2')
    def offline(*a,**k):raise RuntimeError('Network disabled in local AI probe')
    socket.socket.connect=offline;socket.create_connection=offline
    from PIL import Image,ImageDraw,ImageFont
    import numpy as np
    import cv2
    from rapidocr_onnxruntime import RapidOCR
    import importlib.metadata as md
    ffmpeg=next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe'))
    def ff(extra):
        subprocess.run([str(ffmpeg),'-hide_banner','-loglevel','error','-nostdin','-y',*map(str,extra)],check=True,capture_output=True,timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    digest=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    source_hash=digest(args.video);report={'kind':'local_ai_feasibility','productionIntegrated':False,'networkDisabled':True,'sourceSHA256':source_hash,'checks':[],
        'versions':{k:md.version(k) for k in ('faster-whisper','ctranslate2','rapidocr-onnxruntime','onnxruntime')}}
    def check(name,value):
        if not value:raise AssertionError(name)
        report['checks'].append(name);print('PASS '+name,flush=True)
    try:
        started=time.perf_counter();ocr=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1,det_use_cuda=False,rec_use_cuda=False,cls_use_cuda=False)
        report['ocrLoadSeconds']=round(time.perf_counter()-started,3)
        control=Image.new('RGB',(1000,120),'white');ImageDraw.Draw(control).text((20,20),'本地字幕识别测试 2026',font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',48),fill='black');control.save(out/'ocr-control.png')
        rows,_=ocr(np.array(control));text=' '.join(row[1] for row in rows or [])
        report['ocrControlText']=text;check('known_chinese_control_recognized','字幕识别测试' in text)
        results=[]
        # Same user-selected subtitle rectangle as the existing VSR sample.
        region=(360/1254,599/720,535/1254,47/720)
        for second in (2,5,8):
            frame=out/f'frame-{second}.png';ff(['-ss',second,'-i',args.video,'-frames:v','1',frame]);image=Image.open(frame).convert('RGB');w,h=image.size
            x,y,rw,rh=region;left,top,right,bottom=round(x*w),round(y*h),round((x+rw)*w),round((y+rh)*h)
            crop=image.crop((left,top,right,bottom));started=time.perf_counter();rows,_=ocr(np.array(crop));elapsed=time.perf_counter()-started
            result={'second':second,'seconds':round(elapsed,3),'items':[{'text':row[1],'score':float(row[2]),'box':[[float(p[0]+left),float(p[1]+top)] for p in row[0]]} for row in rows or []]};results.append(result)
            draw=ImageDraw.Draw(image)
            for row in result['items']:draw.line([tuple(p) for p in row['box']]+[tuple(row['box'][0])],fill='#22e6a5',width=3)
            image.save(out/f'ocr-detected-{second}.png');print('OCR '+json.dumps(result,ensure_ascii=False),flush=True)
        report['ocrFrames']=results;check('real_video_caption_text_and_boxes_returned',any(r['items'] for r in results))
        audio=out/'sample.wav';ff(['-i',args.video,'-t','12','-vn','-ac','1','-ar','16000',audio])
        from faster_whisper import WhisperModel
        started=time.perf_counter();model=WhisperModel(str(args.model.resolve()),device='cpu',compute_type='int8',cpu_threads=2,num_workers=1,local_files_only=True)
        report['asrLoadSeconds']=round(time.perf_counter()-started,3);started=time.perf_counter()
        segments,info=model.transcribe(str(audio),language='zh',beam_size=5,vad_filter=True,condition_on_previous_text=False)
        items=[{'start':s.start,'end':s.end,'text':s.text} for s in segments];report['asrSeconds']=round(time.perf_counter()-started,3);report['asrSegments']=items
        check('local_speech_returns_nonempty_timed_segments',bool(items) and all(0<=s['start']<s['end']<=12.5 and s['text'].strip() for s in items))
        def timestamp(value):
            ms=round(value*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
        srt='\n\n'.join(f'{i+1}\n{timestamp(s["start"])} --> {timestamp(s["end"])}\n{s["text"].strip()}' for i,s in enumerate(items))+'\n'
        (out/'语音识别样本.srt').write_text(srt,'utf-8');print('ASR '+json.dumps(items,ensure_ascii=False),flush=True)
        check('source_media_unchanged',digest(args.video)==source_hash);report['ok']=True
    finally:(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps({'ok':report['ok'],'checks':len(report['checks']),'output':str(out)},ensure_ascii=False))

if __name__=='__main__':main()
