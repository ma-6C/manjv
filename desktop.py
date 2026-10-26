"""Windows WebView2 desktop entry point, no external browser required."""
import os
from pathlib import Path
import sys
import threading
import traceback

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'vendor'))
import server
import licensing,local_session

def main():
    licensing.verify_distribution(server.APP_HOME)
    import webview
    import ctypes,hashlib
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p];kernel.CreateMutexW.restype=ctypes.c_void_p
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    instance=kernel.CreateMutexW(None,False,'Local\\ManjuStudio.'+hashlib.sha256(str(server.DATA).encode()).hexdigest()[:24])
    if not instance:raise OSError('无法创建本机应用实例')
    if ctypes.get_last_error()==183:
        hwnd=ctypes.windll.user32.FindWindowW(None,'漫剧工坊')
        if hwnd:ctypes.windll.user32.ShowWindow(hwnd,9);ctypes.windll.user32.SetForegroundWindow(hwnd)
        kernel.CloseHandle(instance)
        return
    service = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    service.session=local_session.Session()
    port = service.server_address[1]
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    window = webview.create_window('漫剧工坊', f'http://127.0.0.1:{port}/launch/{service.session.launch}',
        width=1440, height=960, min_size=(1024, 720), background_color='#f7f8fc',
        text_select=True, confirm_close=False)
    def on_closing():
        active = any(j['status'] in ['queued', 'running', 'pausing'] for j in server.JOBS.values()) or bool(server.SOURCE_MANAGER and any(j['status'] in ['queued','running'] for j in server.SOURCE_MANAGER.list())) or any(f['status']=='running' for f in server.STATE.get('studioFlows',{}).get('flows',[]))
        if active:
            return window.create_confirmation_dialog('任务仍在运行', '关闭后任务和已完成检查点会保留，重新打开后可继续。确定关闭？')
        return True
    window.events.closing += on_closing
    try:
        webview.start(gui='edgechromium', debug=False, private_mode=False,icon=str(ROOT/'assets'/'app.ico'),
                      storage_path=str(server.DATA / 'desktop-profile'))
    finally:
        if server.SOURCE_MANAGER:server.SOURCE_MANAGER.shutdown()
        server.shutdown_jobs()
        service.shutdown()
        service.server_close()
        kernel.CloseHandle(instance)

if __name__ == '__main__':
    if '--engine-worker' in sys.argv:
        licensing.verify_distribution(server.APP_HOME)
        licensing.require(server.DATA)
        sys.argv.remove('--engine-worker')
        import engine_bridge
        engine_bridge.main()
        sys.exit(0)
    try:
        if '--install-engine' in sys.argv:
            licensing.verify_distribution(server.APP_HOME)
            import engine_manager
            engine_manager.install(sys.argv[sys.argv.index('--install-engine')+1],server.DATA)
        else:main()
    except Exception:
        text = traceback.format_exc()
        (server.DATA / 'desktop-error.log').write_text(text, encoding='utf-8')
        try:
            import ctypes
            if '--install-engine' not in sys.argv:ctypes.windll.user32.MessageBoxW(0, str(sys.exc_info()[1])+'\n详细记录：'+str(server.DATA/'desktop-error.log'), '漫剧工坊', 16)
        except Exception:pass
        sys.exit(1)
