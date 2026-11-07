"""Hold only a fresh installed-app diagnostic process until its finish marker."""
from pathlib import Path
import json
import os
import socket
import subprocess
import tempfile
import time
import sqlite3
import urllib.request
import urllib.parse
import http.cookiejar
import argparse
import ctypes
import struct
import urllib.error
import hashlib

ROOT = Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--exe',type=Path);parser.add_argument('--version',default='v0.10.10');parser.add_argument('--startup-only',action='store_true');parser.add_argument('--reuse-data',type=Path);parser.add_argument('--state-file',type=Path,default=ROOT/'tmp/native-diagnostic-v10.json');args=parser.parse_args()
if args.exe:exe=args.exe.resolve()
else:
    installed = json.loads((ROOT / 'versions' / args.version / 'installation-reset-report.json').read_text('utf-8'))
    exe=Path(installed['installationDirectory']) / '漫剧工坊.exe'
assert exe.is_relative_to((ROOT/'tmp').resolve())
base = Path(tempfile.mkdtemp(prefix='native-diagnostic-'+args.version+'-held-', dir=ROOT / 'tmp'))
data = args.reuse_data.resolve() if args.reuse_data else base/'data'
if args.reuse_data:
    assert data.is_relative_to((ROOT/'tmp').resolve()) and data.name=='data' and data.is_dir()
    assert data.parent.name.startswith('native-diagnostic-'+args.version+'-held-')
    previous=json.loads((data.parent/'launcher-report.json').read_text('utf-8'))
    assert previous['exitCode']==0 and Path(previous['exe']).resolve()==exe


def own_loopback_ports(pid):
    size=ctypes.c_ulong(0)
    api=ctypes.WinDLL('iphlpapi').GetExtendedTcpTable
    api.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong),ctypes.c_bool,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_ulong]
    api.restype=ctypes.c_ulong
    code=api(None,ctypes.byref(size),False,2,5,0)
    if code!=122:return []
    data=ctypes.create_string_buffer(size.value)
    if api(data,ctypes.byref(size),False,2,5,0):return []
    raw=data.raw;count=struct.unpack_from('<I',raw)[0];ports=[]
    for index in range(count):
        state,address,port,_,_,owner=struct.unpack_from('<6I',raw,4+24*index)
        if state==2 and owner==pid and socket.inet_ntoa(struct.pack('<I',address))=='127.0.0.1':
            ports.append(socket.ntohs(port&65535))
    return ports
with socket.socket() as server:
    server.bind(('127.0.0.1', 0)); port = server.getsockname()[1]
env = os.environ.copy(); env.pop('MANJU_REAL_API_KEY', None)
env.update(MANJU_DATA=str(data), WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS='--remote-debugging-port=' + str(port))
with exe.open('rb') as executable_stream:executable_sha=hashlib.file_digest(executable_stream,'sha256').hexdigest()
started = time.monotonic()
with (base / 'process.log').open('wb') as stream:
    app = subprocess.Popen([str(exe)], cwd=exe.parent, env=env, stdout=stream, stderr=stream,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    report = {'version':args.version,'base': str(base), 'exe': str(exe), 'executableSHA256':executable_sha,'dataDirectory':env['MANJU_DATA'],'pid': app.pid, 'port': port, 'launcherHeldAlive': True,'startedAtEpoch':time.time(),
              'freshAppProfile':not args.reuse_data,
              'timingMethod':'monotonic Popen to own-PID loopback HTTP response; OS file cache not forcibly purged',
              'historyDiscoveryIsNotFirstPageRenderTiming':True}
    args.state_file.write_text(json.dumps(report, ensure_ascii=False), 'utf-8')
    print(json.dumps(report, ensure_ascii=True), flush=True)
    history = data / 'desktop-profile/EBWebView/Default/History'
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    try:
        while app.poll() is None and time.monotonic() - started < 1200 and not (base / 'finish.txt').exists():
            if 'firstLoopbackHTTPResponseSeconds' not in report:
                for listener in own_loopback_ports(app.pid):
                    try:
                        try:
                            response=urllib.request.urlopen('http://127.0.0.1:'+str(listener)+'/',timeout=.3)
                        except urllib.error.HTTPError as failure:
                            response=failure
                        with response:
                            report.update(firstLoopbackHTTPResponseSeconds=round(time.monotonic()-started,3),firstHTTPStatus=response.code,appServicePort=listener)
                            args.state_file.write_text(json.dumps(report,ensure_ascii=False),'utf-8')
                            print('ACTUAL_EXE_FIRST_OWN_HTTP_SECONDS',report['firstLoopbackHTTPResponseSeconds'],flush=True)
                    except OSError:pass
            if args.startup_only and 'firstLoopbackHTTPResponseSeconds' in report:break
            if not args.reuse_data and not any(key in report for key in ('activationPageReadySeconds','workbenchPageReadySeconds')) and history.is_file():
                try:
                    with sqlite3.connect(history.as_uri() + '?mode=ro&immutable=1', uri=True, timeout=0.2) as connection:
                        urls = [row[0] for row in connection.execute('SELECT url FROM urls ORDER BY last_visit_time DESC')]
                    launch = next(url for url in urls if urllib.parse.urlsplit(url).path.startswith('/launch/'))
                    assert urllib.parse.urlsplit(launch).hostname == '127.0.0.1'
                    with opener.open(launch, timeout=1) as response:
                        landing=response.read()
                        if b'activation-form' in landing:
                            report['activationPageReadySeconds'] = round(time.monotonic() - started, 3)
                            args.state_file.write_text(json.dumps(report, ensure_ascii=False), 'utf-8')
                            print('ACTUAL_EXE_ACTIVATION_HTTP_READY_SECONDS', report['activationPageReadySeconds'], flush=True)
                        elif b'id="content"' in landing:
                            report['workbenchPageReadySeconds'] = round(time.monotonic() - started, 3)
                            args.state_file.write_text(json.dumps(report, ensure_ascii=False), 'utf-8')
                            print('ACTUAL_EXE_WORKBENCH_HTTP_READY_SECONDS', report['workbenchPageReadySeconds'], flush=True)
                except (OSError, ValueError, sqlite3.Error, StopIteration):
                    pass
            time.sleep(.2 if 'firstLoopbackHTTPResponseSeconds' not in report else 1)
    finally:
        if app.poll() is None:
            subprocess.run(['taskkill', '/PID', str(app.pid), '/T', '/F'], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=15, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            try:app.wait(timeout=5)
            except subprocess.TimeoutExpired:pass
        report.update(elapsed=round(time.monotonic() - started, 3), exitCode=app.poll())
        (base / 'launcher-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
