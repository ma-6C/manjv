"""Open the real desktop entry with disposable media and isolated application data."""
from pathlib import Path
import json
import os
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
BASE=Path(tempfile.mkdtemp(prefix='commercial-desktop-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data')
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import server as s
source=BASE/'素材'/'桌面流程验收';source.mkdir(parents=True)
for number in (1,2):
    s.ff(['-f','lavfi','-i',f'testsrc2=size=320x180:rate=25:duration={number+1}',
          '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-shortest',
          '-c:v','libx264','-preset','ultrafast','-c:a','aac',str(source/f'第{number}集.mp4')])
s.STATE['config']=s.validate_config(s.STATE['config']|{'source':str(source.parent),'output':str(BASE/'成片'),
    'width':320,'height':180,'segmentSeconds':2,'gpu':False,'subtitleMode':'local','subtitleAuto':True,
    'autoCover':True,'autoRecords':True,'autoCost':True,'autoText':False,'autoAICover':False,
    'costRows':[{'name':'桌面流程验收','amount':1000}]})
project=s.scan(str(source.parent))['projects'][0];project.update(rights=True,intro='本机合成媒体，只用于核验桌面完整制作流程。')
s.save()
(ROOT/'tmp/commercial-desktop-host.json').write_text(json.dumps({'base':str(BASE),'pid':os.getpid(),'projectId':project['id']},ensure_ascii=False),'utf-8')
print(json.dumps({'base':str(BASE),'pid':os.getpid()},ensure_ascii=True),flush=True)
import desktop
desktop.main()
