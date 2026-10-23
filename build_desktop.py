"""Bundle the desktop runtime into a portable folder, without user data/secrets."""
from pathlib import Path
import os
import sys
import argparse
import re
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--version',default='v0.2.0')
args=parser.parse_args()
if not re.fullmatch(r'v\d+\.\d+\.\d+',args.version):raise ValueError('版本目录格式应为 v0.2.0')
destination=ROOT/'release'/args.version
if (destination/'漫剧工坊'/'data').exists():
    raise RuntimeError('目标版本目录含用户数据，请指定新的 --version，避免覆盖数据。')
sys.path.insert(0,str(ROOT/'tmp/build-tools'))
sys.path.insert(0,str(ROOT/'vendor'))
from PyInstaller.__main__ import run
run([
    str(ROOT/'desktop.py'),'--name','漫剧工坊','--noconsole','--onedir','--noconfirm','--clean',
    '--distpath',str(destination),'--workpath',str(ROOT/'tmp/pyinstaller'),'--specpath',str(ROOT/'tmp'),
    '--paths',str(ROOT/'vendor'),'--icon',str(ROOT/'assets/app.ico'),
    '--add-data',str(ROOT/'web')+os.pathsep+'web',
    '--add-data',str(ROOT/'assets')+os.pathsep+'assets',
    '--add-data',str(ROOT/'engines/guoapp-core')+os.pathsep+'engines/guoapp-core',
    '--add-data',str(ROOT/'engines/social-auto-upload/uploader')+os.pathsep+'engines/social-auto-upload/uploader',
    '--add-data',str(ROOT/'engines/social-auto-upload/utils')+os.pathsep+'engines/social-auto-upload/utils',
    '--add-data',str(ROOT/'engines/social-auto-upload/conf.py')+os.pathsep+'engines/social-auto-upload',
    '--add-data',str(ROOT/'engines/social-auto-upload/LICENSE')+os.pathsep+'engines/social-auto-upload',
    '--collect-all','webview','--collect-all','pythonnet','--collect-all','clr_loader',
    '--collect-all','imageio_ffmpeg','--collect-all','patchright','--collect-all','segno',
    '--collect-all','cv2','--collect-all','loguru','--hidden-import','webview.platforms.edgechromium',
    '--hidden-import','webview.platforms.winforms','--hidden-import','engine_bridge','--hidden-import','official_hongguo_share',
])
