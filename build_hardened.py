"""Compile product core, bundle clean runtime, sign its integrity manifest."""
from pathlib import Path
import sys,os,shutil,ast,json,hashlib,subprocess,argparse,re
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--version',default='v0.5.0');parser.add_argument('--prepare-only',action='store_true',help='Compile and bundle without signing; the result remains unlaunchable until signed')
parser.add_argument('--issuer',type=Path,default=ROOT/'授权管理/当前签发工具-v2/授权签发工具.exe')
options=parser.parse_args();version=options.version
if not re.fullmatch(r'v\d+\.\d+\.\d+',version):raise ValueError('版本号无效')
STAGE=ROOT/('tmp/hardened-stage-'+version);STAGE.mkdir(parents=True,exist_ok=True)
DIST=ROOT/'release'/version/'漫剧工坊'
if (DIST/'data').exists():raise RuntimeError('构建目录含用户数据，请改用新的版本目录')
MODULES=['server','ai_providers','api_connections','media_download','engine_bridge','licensing','win_security','release_key','runtime_paths','local_session','engine_manager','promotions','task_progress','hongguo_source','guoapp_source','official_hongguo_share','source_imports','episode_selection','gpu_encoding','transform_tools','track_sheets','jianying_projects','highlight_render','vsr_pool','lama_local','publish_materials','publish_workflow','publish_browser','project_evidence','studio_flow','studio_flow_adapter','jianying_automation']
for module in MODULES:shutil.copy2(ROOT/(module+'.py'),STAGE/(module+'.py'))
shutil.copy2(ROOT/'desktop.py',STAGE/'desktop.py')
imports=set()
for module in MODULES:
    tree=ast.parse((ROOT/(module+'.py')).read_text('utf-8'))
    for node in ast.walk(tree):
        if isinstance(node,(ast.Import,ast.ImportFrom)):
            if isinstance(node,ast.ImportFrom) and (node.level or node.module=='__future__'):continue
            imports.add(ast.unparse(node))
(STAGE/'package_imports.py').write_text("if globals().get('_BUILD_ANALYSIS_ONLY'):\n"+'\n'.join('    '+x for x in sorted(imports))+'\n','utf-8')
(STAGE/'desktop.py').write_text('import package_imports\n'+(ROOT/'desktop.py').read_text('utf-8'),'utf-8')
(STAGE/'setup.py').write_text("from setuptools import setup\nfrom Cython.Build import cythonize\nsetup(ext_modules=cythonize("+repr([m+'.py' for m in MODULES])+",compiler_directives={'language_level':3,'binding':False,'embedsignature':False},nthreads=0))\n",'utf-8')
env=os.environ.copy();env['PYTHONPATH']=str(ROOT/'tmp/hardening-tools');env.pop('DISTUTILS_USE_SDK',None)
subprocess.run([sys.executable,'setup.py','build_ext','--inplace'],cwd=STAGE,env=env,check=True)
# Only compiled product modules enter the analysis path. Generated C stays in build workspace.
for m in MODULES:(STAGE/(m+'.py')).unlink()
sys.path[:0]=[str(ROOT/'tmp/build-tools'),str(ROOT/'vendor'),str(STAGE)]
os.chdir(STAGE)
from PyInstaller.__main__ import run
args=[str(STAGE/'desktop.py'),'--name','漫剧工坊','--noconsole','--onedir','--noconfirm','--clean','--distpath',str(DIST.parent),'--workpath',str(ROOT/('tmp/pyinstaller-hardened-'+version)),'--specpath',str(STAGE),'--paths',str(STAGE),'--paths',str(ROOT/'vendor'),'--icon',str(ROOT/'assets/app.ico')]
for folder in ['web','assets']:args+=['--add-data',str(ROOT/folder)+os.pathsep+folder]
args+=['--add-data',str(ROOT/'engines/guoapp-core')+os.pathsep+'engines/guoapp-core']
args+=['--add-data',str(ROOT/'engines/jianying-draft')+os.pathsep+'engines/jianying-draft']
for folder in ['uploader','utils','conf.py','LICENSE']:args+=['--add-data',str(ROOT/'engines/social-auto-upload'/folder)+os.pathsep+('engines/social-auto-upload' if '.' in folder or folder=='LICENSE' else 'engines/social-auto-upload/'+folder)]
for module in ['webview','pythonnet','clr_loader','imageio_ffmpeg','patchright','segno','cv2','loguru','pyJianYingDraft','pymediainfo','imageio','uiautomation','comtypes']:args+=['--collect-all',module]
for module in MODULES+['webview.platforms.edgechromium','webview.platforms.winforms','package_imports']:args+=['--hidden-import',module]
run(args)
for cached in list(DIST.rglob('*.pyc')):
    if '__pycache__' in cached.parts:
        if not cached.resolve().is_relative_to(DIST.resolve()):raise ValueError('缓存路径超出发行目录')
        cached.unlink()
for folder in sorted(DIST.rglob('__pycache__'),key=lambda p:len(p.parts),reverse=True):
    if folder.resolve().is_relative_to(DIST.resolve()) and not any(folder.iterdir()):folder.rmdir()
if options.prepare_only:
    # Never leave a stale signature attached to a changed build. Production
    # verification is unchanged and will reject this staging bundle.
    (DIST/'integrity.json').unlink(missing_ok=True)
    (DIST.parent/'未完成发行-请勿发送.txt').write_text('当前仅完成编译准备，尚未签署发行清单，不能发给客户。生产签名与授权校验保持启用。\n','utf-8-sig')
    print('UNSIGNED_PREPARATION_ONLY',str(DIST),flush=True);sys.exit(0)
subprocess.run([sys.executable,str(ROOT/'sign_distribution.py'),'--version',version,'--issuer',str(options.issuer.resolve())],cwd=ROOT,check=True)
print('HARDENED_BUILD_OK',str(DIST),flush=True)
