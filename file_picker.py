"""Owned desktop dialogs and an absolute-path PowerShell browser fallback."""
from pathlib import Path
import json,os,shutil,subprocess,threading

LOCK=threading.Lock()
FILTERS={
 'folder':None,'editor':('JianyingPro.exe','JianyingPro.exe'),
 'python':('Python runtime','*.exe'),'engine':('AI engine','*.zip'),
 'template':('Word template','*.docx'),'image':('Images','*.jpg;*.jpeg;*.png;*.webp'),
 'images':('Images','*.jpg;*.jpeg;*.png;*.webp'),
 'documents':('Reports','*.pdf;*.docx;*.csv;*.jpg;*.jpeg;*.png;*.webp'),
 'videos':('Video files','*.mp4;*.mov;*.mkv;*.avi;*.m4v;*.webm;*.ts'),
 'audio':('Audio','*.mp3;*.wav;*.m4a;*.aac;*.flac;*.ogg'),
}

def specification(body):
    mode=body.get('mode','folder')
    if mode not in FILTERS:raise ValueError('不支持的文件选择类型')
    return {'mode':mode,'folder':mode=='folder','multiple':mode in ('images','documents') or mode=='videos' and body.get('multiple') is not False,'filter':FILTERS[mode],
            'plural':mode in ('images','documents','videos')}

def normalize(selection,spec):
    paths=[selection] if isinstance(selection,str) else list(selection or [])
    if any(not isinstance(p,str) for p in paths):raise ValueError('文件选择窗口返回了无效路径')
    return {'paths':paths} if spec['plural'] else {'path':paths[0] if paths else ''}

def powershell_executable():
    root=Path(os.environ.get('SystemRoot') or os.environ.get('WINDIR') or 'C:/Windows')
    candidates=[root/'System32/WindowsPowerShell/v1.0/powershell.exe',root/'Sysnative/WindowsPowerShell/v1.0/powershell.exe']
    for path in candidates:
        if path.is_file():return str(path)
    for name in ('powershell.exe','pwsh.exe'):
        found=shutil.which(name)
        if found:return str(Path(found).resolve())
    raise RuntimeError('文件选择窗口无法启动：未找到 Windows PowerShell。可在路径输入框中直接粘贴完整路径。检查位置：'+str(candidates[0]))

def script_for(spec):
    if spec['folder']:
        setup="$d=New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description='选择文件夹';"
        selected='@($d.SelectedPath)'
    else:
        label,extensions=spec['filter']
        setup="$d=New-Object System.Windows.Forms.OpenFileDialog; $d.RestoreDirectory=$true; $d.Filter='"+label+'|'+extensions+"'; $d.Multiselect="+('$true' if spec['multiple'] else '$false')+';'
        selected='@($d.FileNames)'
    return "[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false); $ErrorActionPreference='Stop'; Add-Type -AssemblyName System.Windows.Forms; $d=$null; $owner=$null; try {"+setup+" $owner=New-Object System.Windows.Forms.Form; $owner.TopMost=$true; $owner.ShowInTaskbar=$false; $owner.Opacity=0; $owner.Show(); if($d.ShowDialog($owner) -eq 'OK'){ConvertTo-Json -Compress -InputObject "+selected+"}else{Write-Output '[]'}}catch{[Console]::Error.WriteLine($_.Exception.ToString());exit 1}finally{if($d){$d.Dispose()};if($owner){$owner.Close();$owner.Dispose()}}"

def native_selection(window,spec):
    """Marshal onto pywebview's actual Windows STA owner thread."""
    from System import Action
    from webview import FileDialog
    result={}
    def show():
        try:
            filters=() if spec['folder'] else (spec['filter'][0]+' ('+spec['filter'][1]+')',)
            result['paths']=window.create_file_dialog(FileDialog.FOLDER if spec['folder'] else FileDialog.OPEN,
                directory=str(Path.home()),allow_multiple=spec['multiple'],file_types=filters)
        except Exception as error:result['error']=error
    control=window.native
    if control is None:raise RuntimeError('桌面窗口尚未就绪，请稍后再打开文件选择窗口')
    if control.InvokeRequired:control.Invoke(Action(show))
    else:show()
    if result.get('error'):raise RuntimeError('系统文件选择窗口未能打开：'+str(result['error'])) from result['error']
    return result.get('paths')

def choose(body,native=None):
    spec=specification(body)
    if not LOCK.acquire(blocking=False):raise ValueError('已有文件选择窗口打开，请先在任务栏中完成或取消选择')
    try:
        if native:return normalize(native(spec),spec)
        executable=powershell_executable()
        try:
            proc=subprocess.run([executable,'-NoProfile','-STA','-Command',script_for(spec)],capture_output=True,timeout=180,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except FileNotFoundError as error:raise RuntimeError('文件选择窗口启动程序不存在：'+executable+'。可直接粘贴路径。') from error
        except subprocess.TimeoutExpired as error:raise RuntimeError('文件选择窗口等待超时，请重新打开并完成或取消选择') from error
        if proc.returncode:raise RuntimeError('系统文件选择窗口未能打开：'+proc.stderr.decode('utf-8-sig','replace')[-1200:])
        try:selection=json.loads(proc.stdout.decode('utf-8-sig','replace').strip() or '[]')
        except ValueError as error:raise RuntimeError('文件选择窗口没有返回有效路径，请重新选择或直接粘贴路径') from error
        return normalize(selection,spec)
    finally:LOCK.release()
