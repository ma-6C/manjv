"""Temporary desktop harness for the same native picker used by desktop.py."""
from pathlib import Path
import json,os,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
BASE=Path(tempfile.mkdtemp(prefix='native-picker-',dir=ROOT/'tmp'))
(BASE/'中文选择目录').mkdir()
sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import file_picker,webview
events=[]
class API:
    def choose(self,mode):
        previous=os.environ.get('PATH','');os.environ['PATH']=''
        try:
            value=file_picker.choose({'mode':mode},native=lambda spec:file_picker.native_selection(window,spec))
            events.append({'mode':mode,'result':value,'emptyPath':True})
            (ROOT/'tmp/file-picker-native-latest.json').write_text(json.dumps({'base':str(BASE),'events':events},ensure_ascii=False,indent=2),'utf-8')
            return value
        finally:os.environ['PATH']=previous
html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>文件选择验证</title><style>body{font:16px "Microsoft YaHei";padding:32px;background:#f7f8fc;color:#253044}button{padding:12px 20px;margin:10px 12px 10px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:16px;background:white}</style><h1>文件选择验证</h1><p>使用桌面版相同的原生选择器；调用时清空本进程 PATH。</p><button onclick="pick('folder')">选择文件夹</button><button onclick="pick('python')">选择引擎 Python</button><pre id="result">等待选择</pre><script>async function pick(mode){document.querySelector('#result').textContent='正在打开选择窗口';try{document.querySelector('#result').textContent=JSON.stringify(await pywebview.api.choose(mode),null,2)}catch(e){document.querySelector('#result').textContent=String(e)}}</script></html>'''
window=webview.create_window('漫剧工坊 · 文件选择验证',html=html,js_api=API(),width=820,height=500)
(ROOT/'tmp/file-picker-native-host.json').write_text(json.dumps({'pid':os.getpid(),'base':str(BASE)},ensure_ascii=False),'utf-8')
webview.start(gui='edgechromium',debug=False,private_mode=True,storage_path=str(BASE/'profile'))
