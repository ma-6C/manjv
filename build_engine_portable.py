"""Assemble relocatable offline STTN environment; no developer paths or user config."""
from pathlib import Path
import shutil,json,os,time
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'tmp'/'portable-engine-v1';BASE.mkdir(parents=True,exist_ok=True)
PYROOT=Path(r'C:\Users\yumda\.cache\codex-runtimes\codex-primary-runtime\dependencies\python')
def ignore(directory,names):
 return {n for n in names if n in ['__pycache__','.git','.pytest_cache','tests','test','idlelib','tkinter','turtledemo'] or n.endswith(('.pyc','.pyo','.log')) or n=='direct_url.json'}
def copy(src,dst):
 if src.is_dir():shutil.copytree(src,dst,ignore=ignore,dirs_exist_ok=True)
 else:dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
runtime=BASE/'python';runtime.mkdir(exist_ok=True)
for p in PYROOT.iterdir():
 if p.suffix in ['.exe','.dll'] or p.name=='LICENSE.txt':copy(p,runtime/p.name)
copy(PYROOT/'DLLs',runtime/'DLLs')
# Base standard library, excluding the Codex host's global packages.
shutil.copytree(PYROOT/'Lib',runtime/'Lib',dirs_exist_ok=True,ignore=lambda d,n:ignore(d,n)|({'site-packages'} if Path(d)==PYROOT/'Lib' else set()))
copy(ROOT/'engines/vsr-env/Lib/site-packages',runtime/'Lib/site-packages')
# numpy.testing imports this small runtime helper through SciPy array-api compatibility.
shutil.copytree(ROOT/'engines/vsr-env/Lib/site-packages/numpy/_core/tests',runtime/'Lib/site-packages/numpy/_core/tests',dirs_exist_ok=True)
(runtime/'python312._pth').write_text('.\nDLLs\nLib\nLib/site-packages\n../video-subtitle-remover\nimport site\n','utf-8')
engine=BASE/'video-subtitle-remover'
copy(ROOT/'engines/video-subtitle-remover/backend',engine/'backend')
for name in ['LICENSE','README.md','README_en.md','requirements.txt']:copy(ROOT/'engines/video-subtitle-remover'/name,engine/name)
(engine/'config').mkdir(exist_ok=True)
(engine/'config/config.json').write_text(json.dumps({'Main':{'InpaintMode':'STTN_AUTO'},'Updates':{'CheckUpdateOnStartup':False}},indent=2),'utf-8')
manifest={'format':1,'id':'vsr-1.4.0-sttn-cu126','python':'python/python.exe','root':'video-subtitle-remover','mode':'sttn-auto',
 'engineCommit':'e109b9ddc1d0e8f153199dfa05c1d767546906d8','pythonVersion':'3.12.14','torch':'2.7.0+cu126','source':'https://github.com/YaoFANGUK/video-subtitle-remover'}
(BASE/'engine.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({'base':str(BASE),'bytes':sum(p.stat().st_size for p in BASE.rglob('*') if p.is_file())}),flush=True)
