"""Backed-up draft registration and reversible cover markers, only while closed."""
from pathlib import Path
import csv
import hashlib
import io
import json
import os
import subprocess
import threading
import time
import uuid

LOCK=threading.Lock()


def running():
    if os.name!='nt':raise ValueError('剪映草稿登记需要 Windows')
    tasklist=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/tasklist.exe'
    result=subprocess.run([str(tasklist),'/FI','IMAGENAME eq JianyingPro.exe','/FO','CSV','/NH'],
        capture_output=True,timeout=10,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise ValueError('无法确认剪映进程状态，本次未修改草稿索引')
    rows=csv.reader(io.StringIO(result.stdout.decode('utf-8','replace')))
    return any(row and row[0].casefold()=='jianyingpro.exe' for row in rows)


def token(folder,name):
    return hashlib.sha256((str(Path(folder).resolve())+'\0'+name).encode()).hexdigest()[:8]


def mark_cover(folder,name,modified=None):
    from PIL import Image,ImageDraw
    folder=Path(folder);source=folder/'Resources/封面.jpg'
    if not source.is_file():return None
    path=folder/'manju-card.png';code=token(folder,name)
    # Current Jianying home cards are square; a landscape marker is cropped
    # and cannot be decoded there. The marker is removed after editor entry.
    with Image.open(source) as original:image=original.convert('RGB').resize((640,640))
    draw=ImageDraw.Draw(image);draw.rectangle((1,1,638,638),outline=(245,0,220),width=18)
    bits=f'{int(code,16):032b}'
    for i,bit in enumerate(bits):
        row,col=divmod(i,8);x=64+col*64;y=128+row*96
        draw.rectangle((x,y,x+63,y+95),fill=(250,250,250) if bit=='1' else (10,10,10))
    image.save(path,'PNG')
    (folder/'manju-card.json').write_text(json.dumps({'token':code,'source':'Resources/封面.jpg','active':True}),'utf-8')
    # Jianying refreshes its root index from each draft's own metadata on
    # startup. Updating only the index cover is therefore immediately undone.
    # Change only our newly imported, still-readable metadata copy.
    meta_path=folder/'draft_meta_info.json'
    try:meta=json.loads(meta_path.read_text('utf-8-sig'))
    except (ValueError,UnicodeError):meta=None
    if isinstance(meta,dict):
        meta['draft_cover']=str(path)
        if modified is not None:meta['tm_draft_modified']=modified
        meta_path.write_text(json.dumps(meta,ensure_ascii=False,indent=2),'utf-8')
    return path


def restore_cover(folder):
    from PIL import Image
    folder=Path(folder);state=folder/'manju-card.json'
    if not state.is_file():return
    info=json.loads(state.read_text('utf-8'))
    if not info.get('active'):return
    source=folder/'Resources/封面.jpg';target=folder/'manju-card.png'
    with Image.open(source) as image:image.convert('RGB').save(target,'PNG')
    info['active']=False;state.write_text(json.dumps(info),'utf-8')


def find_mark(image,code):
    """Locate a colored cover border and verify all 32 target-specific bits."""
    import cv2
    import numpy as np
    rgb=np.asarray(image.convert('RGB'));mask=((rgb[:,:,0]>190)&(rgb[:,:,1]<65)&(rgb[:,:,2]>160)).astype('uint8')
    count,_,stats,_=cv2.connectedComponentsWithStats(mask,connectivity=8)
    matches=[];expected=f'{int(code,16):032b}'
    for x,y,w,h,area in stats[1:count]:
        square=.8<w/h<1.2
        if w<60 or h<32 or not (square or 1.35<w/h<2.1) or area<w*h*.035:continue
        decoded=''
        for i in range(32):
            row,col=divmod(i,8)
            px=int(x+w*(96+col*64)/640)
            py=int(y+h*(176+row*96)/640) if square else int(y+h*(99+row*54)/360)
            value=rgb[min(py,rgb.shape[0]-1),min(px,rgb.shape[1]-1)]
            if max(value)-min(value)>45:break
            decoded+='1' if min(value)>160 else '0' if max(value)<90 else '?'
        if decoded==expected:matches.append((int(x+w/2),int(y+h/2)))
    return matches[0] if len(matches)==1 else None


def first_draft(folder):
    """Confirm that the first visible registered draft is our imported copy."""
    import jianying_projects
    folder=Path(folder).resolve();index,_=jianying_projects._open_index(folder)
    native=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'JianyingPro/User Data/Projects/com.lveditor.draft'
    root=native if (native/'root_meta_info.json').is_file() else folder.parent
    try:
        value=json.loads((root/'root_meta_info.json').read_text('utf-8-sig'))
        rows=value.get('all_draft_store',[])
        if not isinstance(rows,list):return False
        visible=[row for row in rows if isinstance(row,dict) and not row.get('draft_is_invisible') and not row.get('tm_draft_removed')]
        if not visible:return False
        first=visible[0]
        same=(first.get('draft_name')==index['name'] and
                isinstance(first.get('draft_fold_path'),str) and Path(first['draft_fold_path']).resolve()==folder and
                isinstance(first.get('draft_id'),str) and bool(first['draft_id']))
        if not same:return False
        if not index.get('editorDraftId') or first['draft_id']==index['editorDraftId']:return True
        # Jianying can assign a fresh library ID while scanning an imported
        # draft. Accept that only when its readable metadata independently
        # agrees with the exact indexed ID, name and directory.
        metadata=folder/'draft_meta_info.json'
        if metadata.is_symlink() or metadata.stat().st_size>8*1024**2:return False
        meta=json.loads(metadata.read_text('utf-8-sig'))
        return (meta.get('draft_id')==first['draft_id'] and meta.get('draft_name')==index['name'] and
                isinstance(meta.get('draft_fold_path'),str) and Path(meta['draft_fold_path']).resolve()==folder)
    except (OSError,ValueError,TypeError,KeyError):return False


def register(folder,opts):
    """Add only this generated draft, never drop another root-index entry."""
    import jianying_projects
    folder=Path(folder).expanduser().resolve();index,_=jianying_projects._open_index(folder)
    if not index.get('editorImportedAt'):raise ValueError('只能登记本工具已导入的草稿副本')
    draft_root=folder.parent
    native=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'JianyingPro/User Data/Projects/com.lveditor.draft'
    # Native projects can live on another disk while their shared index stays
    # under the user's Jianying profile. Do not write a disconnected index
    # beside an arbitrary portable project directory.
    root=native if (native/'root_meta_info.json').is_file() else draft_root
    path=root/'root_meta_info.json'
    if not opts.get('registerIndex',True):return {'indexModified':False,'indexPending':True,'message':'已复制草稿，未启用草稿列表登记'}
    with LOCK:
        if running():return {'indexModified':False,'indexPending':True,'message':'草稿已复制。请先在剪映保存并退出，再点击自动打开；退出后才能登记并置顶索引'}
        if path.is_symlink() or (path.exists() and path.stat().st_size>32*1024**2):raise ValueError('剪映草稿索引路径或大小无效')
        original=path.read_bytes() if path.exists() else None
        data=json.loads(original.decode('utf-8-sig')) if original is not None else {'all_draft_store':[],'draft_ids':0,'root_path':str(root)}
        rows=data.get('all_draft_store')
        if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):raise ValueError('当前剪映索引格式不支持，原索引保持不变')
        ids=data.get('draft_ids',0)
        if not (type(ids) is int and ids>=0) and not (isinstance(ids,list) and all(isinstance(v,str) for v in ids)):
            raise ValueError('当前剪映索引的草稿编号格式不支持，原索引保持不变')
        matches=[row for row in rows if isinstance(row.get('draft_fold_path'),str) and Path(row['draft_fold_path']).resolve()==folder]
        if len(matches)>1:raise ValueError('索引中存在多个同路径工程，请先在剪映核对')
        if matches:
            # Jianying 11 saves imported draft/meta files in a non-plain form.
            # The native index is the readable authority for an existing row.
            meta=dict(matches[0])
            if meta.get('draft_name')!=index['name']:raise ValueError('工程已在剪映中改名，请核对工程名称后继续')
        else:
            try:meta=json.loads((folder/'draft_meta_info.json').read_text('utf-8-sig'))
            except (ValueError,UnicodeError):
                if not index.get('editorDraftId'):raise ValueError('剪映已保存此工程，但当前索引没有对应条目；请在剪映打开工程后重试') from None
                meta={'draft_id':index['editorDraftId']}
        draft_id=meta.get('draft_id')
        if not isinstance(draft_id,str) or not draft_id:raise ValueError('剪映工程编号缺失，未修改索引')
        for row in rows:
            if row.get('draft_id')==draft_id and Path(row.get('draft_fold_path','')).resolve()!=folder:
                raise ValueError('草稿编号与其他工程冲突，未覆盖其他工程')
        now=int(time.time()*1e6)
        marker=mark_cover(folder,index['name'],now) if opts.get('mouseOpen') else None
        entry={k:v for k,v in meta.items() if k!='draft_materials'}
        cover=folder/'Resources/封面.jpg'
        entry.update(draft_id=draft_id,draft_name=index['name'],draft_fold_path=str(folder),draft_root_path=str(draft_root),
                     draft_json_file=str(folder/'draft_content.json'),draft_cover=str(marker or cover) if marker or cover.is_file() else meta.get('draft_cover',''),
                     tm_draft_create=int(index['createdAt']*1e6),tm_draft_modified=now,tm_draft_removed=0,
                     tm_duration=index['durationUs'],draft_is_invisible=False)
        data['all_draft_store']=[entry]+[row for row in rows if row.get('draft_id')!=draft_id]
        # Native indexes use the numeric value 0 here, not a UUID list. Keep
        # its meaning unchanged; support older list-shaped indexes separately.
        if isinstance(ids,list):data['draft_ids']=[draft_id]+[value for value in ids if value!=draft_id]
        backup=None
        if original is not None:
            backups=root/'.manju-index-backups';backups.mkdir(exist_ok=True)
            backup=backups/('root_meta_info-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]+'.json')
            with backup.open('xb') as stream:stream.write(original)
        temporary=root/('.manju-index-'+uuid.uuid4().hex+'.json')
        try:
            with temporary.open('x',encoding='utf-8') as stream:
                json.dump(data,stream,ensure_ascii=False);stream.flush();os.fsync(stream.fileno())
            if running() or (path.read_bytes() if path.exists() else None)!=original:
                raise ValueError('登记期间剪映启动或索引发生变化，已放弃写入；请退出后重试')
            os.replace(temporary,path)
        finally:temporary.unlink(missing_ok=True)
        return {'indexModified':True,'indexPending':False,'indexRoot':str(root),'indexBackup':str(backup) if backup else '',
                'firstDraftDirectory':str(folder),
                'markerToken':token(folder,index['name']) if marker else '',
                'message':'已备份草稿索引，并登记置顶本工程；下一步启动剪映定位草稿'}
