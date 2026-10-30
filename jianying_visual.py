"""Read visible project identity when current Jianying exposes only Qt panes."""
from pathlib import Path
import hashlib
import re
import tempfile
import threading
import asyncio

_CACHE={}
_LOCK=threading.Lock()


def qt_editor_surface(root,controls):
    ids={str(getattr(c,'AutomationId','') or '') for c in controls}
    return (str(root.AutomationId or '')=='MainWindow' and
            bool(ids & {'MainWindow.surface_main','MainWindow.surface_single_resource_player'}))


def _normalize(text):return re.sub(r'[^a-z0-9\u4e00-\u9fff]','',text.casefold())


def match_identity(text,name):
    normalized=_normalize(text)
    if name and _normalize(name) in normalized:
        return {'projectIdentityVerified':True,'projectTitleVerified':True,'projectMatchMethod':'visible_full_title_ocr'}
    number=re.search(r'_工程_(\d{15})$',name)
    if number and re.search(r'(?<!\d)'+number.group(1)+r'(?!\d)',normalized):
        return {'projectIdentityVerified':True,'projectTitleVerified':False,'projectMatchMethod':'visible_project_number_ocr',
                'matchedProjectToken':number.group(1)}
    # Our automatic import names include a unique 12-hex operation id. Read it
    # from the actual editor header, rather than assuming the first card opened.
    token=re.search(r'_流程_([a-f0-9]{12})(?:[-_]|$)',name)
    if token and token.group(1) in normalized:
        return {'projectIdentityVerified':True,'projectTitleVerified':False,'projectMatchMethod':'visible_project_token_ocr',
                'matchedProjectToken':token.group(1)}
    return {'projectIdentityVerified':False,'projectTitleVerified':False}


def match_properties(text,name):
    normalized=_normalize(text)
    if '草稿名称' not in normalized or '保存位置' not in normalized:return match_identity('',name)
    field=normalized.split('草稿名称',1)[1].split('保存位置',1)[0]
    value=match_identity(field,name)
    if value['projectIdentityVerified']:
        value.update(projectTitleVerified=False,projectMatchMethod='visible_project_name_property_ocr')
    return value


def ocr(image):
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage import StorageFile
    from winrt.windows.graphics.imaging import BitmapDecoder
    import runtime_paths
    cache=runtime_paths.data_home()/'editor-identity-cache';cache.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='project-',dir=cache) as temp:
        path=Path(temp)/'header.png';image.save(path,'PNG')
        async def read():
            file=await StorageFile.get_file_from_path_async(str(path))
            stream=await file.open_read_async()
            try:
                decoder=await BitmapDecoder.create_async(stream)
                bitmap=await decoder.get_software_bitmap_async()
                try:
                    engine=OcrEngine.try_create_from_user_profile_languages()
                    if engine is None:raise ValueError('Windows OCR 语言组件不可用')
                    return (await engine.recognize_async(bitmap)).text
                finally:bitmap.close()
            finally:stream.close()
        return asyncio.run(asyncio.wait_for(read(),12))


def visible_identity(root,name):
    if not name:return {'projectIdentityVerified':False,'projectTitleVerified':False}
    from PIL import ImageGrab
    import ctypes
    from ctypes import wintypes as wt
    user=ctypes.WinDLL('user32');user.GetForegroundWindow.restype=wt.HWND
    if int(user.GetForegroundWindow() or 0)!=root.NativeWindowHandle:
        return {'projectIdentityVerified':False,'projectTitleVerified':False,'identityDiagnostic':'请将剪映工程窗口置于前台以核对工程编号'}
    rect=root.BoundingRectangle
    if rect.width()<600 or rect.height()<400:return {'projectIdentityVerified':False,'projectTitleVerified':False}
    # Restrict OCR to the visible title strip; exclude account and editor text.
    box=(rect.left+round(rect.width()*.28),rect.top,rect.left+round(rect.width()*.76),rect.top+52)
    image=ImageGrab.grab(bbox=box,all_screens=True).convert('RGB')
    key=(str(root.NativeWindowHandle),root.ProcessId,name,hashlib.sha256(image.tobytes()).hexdigest())
    with _LOCK:
        if key in _CACHE:return dict(_CACHE[key])
    try:
        readings=[];value=match_identity('',name)
        # Qt renders small antialiased header text. Try independent contrast
        # views, but keep identity matching exact; never fuzzy-match project IDs.
        focused=image.crop((round(image.width*.12),0,round(image.width*.78),image.height))
        variants=(image,focused,focused.convert('L').point(lambda p:255 if p>155 else 0))
        for variant in variants:
            width=min(2500,variant.width*4)
            text=ocr(variant.resize((width,round(variant.height*width/variant.width))).convert('RGB'))
            readings.append(text);value=match_identity(text,name)
            if value['projectIdentityVerified']:break
        if not value['projectIdentityVerified']:
            # Current Qt builds also show the actual draft name above its save
            # location. Match only that labelled name field, never the path or
            # selected media properties, which can reference a different draft.
            panel=ImageGrab.grab(bbox=(rect.left+round(rect.width()*.72),rect.top+round(rect.height()*.07),
                rect.right-8,rect.top+round(rect.height()*.24)),all_screens=True).convert('RGB')
            width=min(2500,panel.width*3)
            text=ocr(panel.resize((width,round(panel.height*width/panel.width))))
            readings.append(text);value=match_properties(text,name)
        if not value['projectIdentityVerified']:value['identityDiagnostic']='可见工程名称未匹配：'+readings[-1][:500]
    except (OSError,ValueError,ImportError,RuntimeError,TimeoutError) as error:
        return {'projectIdentityVerified':False,'projectTitleVerified':False,'identityDiagnostic':str(error)[:600]}
    with _LOCK:
        if len(_CACHE)>32:_CACHE.clear()
        if value['projectIdentityVerified']:_CACHE[key]=value
    return value
