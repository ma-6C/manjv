"""Bounded HTTPS media download for cloud subtitle results; no API credentials."""
from pathlib import Path
import time,urllib.parse,urllib.request

def download(url,target,cancel,max_bytes=1024*1024*1024,progress=None):
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:raise ValueError('输出地址必须是HTTPS')
    partial=Path(str(target)+'.part');total=0
    # Media requests never carry the API credential.
    with urllib.request.urlopen(url,timeout=90) as response,partial.open('wb') as f:
        if urllib.parse.urlsplit(response.geturl()).scheme!='https':raise ValueError('视频下载重定向到了非HTTPS地址')
        length=response.headers.get('Content-Length','')
        expected=int(length) if length.isdigit() and int(length)>0 else None
        if expected and expected>max_bytes:raise ValueError('单个输出超过1GB，请在平台下载')
        last=0
        if progress:progress(0,expected)
        while True:
            if cancel.is_set():raise InterruptedError('下载已暂停')
            chunk=response.read(64*1024)
            if not chunk:break
            total+=len(chunk)
            if total>max_bytes:raise ValueError('单个输出超过1GB，请在平台下载')
            f.write(chunk)
            if progress and time.monotonic()-last>=.25:progress(total,expected);last=time.monotonic()
        if expected and total!=expected:raise ValueError('下载文件不完整，请继续原任务重试下载')
        if progress:progress(total,expected)
    if not total:raise ValueError('视频下载为空')
    partial.replace(target)
